import asyncio
import logging
import os
import re
import threading
import time
from typing import Optional

import certifi

# 部分精简系统镜像或本地 Python 没有完整 CA 路径，显式使用 certifi；
# 仍然执行正常 TLS 证书校验，不会关闭 HTTPS/WSS 安全检查。
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from connector.coze_client import CozeAPIError, CozeClient, merge_stream_text
from connector.feishu import FeishuClient, IncomingMessage, extract_file_text, parse_event
from connector.settings import Settings
from connector.store import Store

logger = logging.getLogger(__name__)
NEW_CHAT_RE = re.compile(
    r"^(新建对话|新对话|开始新对话|开启新对话|重新对话|重置对话|"
    r"清空上下文|清除上下文|重新开始|reset|newchat|newconversation)$",
    re.IGNORECASE,
)


class Connector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.database_path)
        self.feishu = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
        self.coze = CozeClient(
            settings.coze_api_base_url,
            settings.coze_api_token,
            settings.coze_project_id,
            settings.request_timeout_seconds,
        )
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._chat_locks: dict[str, asyncio.Lock] = {}

    def on_event(self, data) -> None:
        msg = parse_event(data)
        if msg is None or self.loop is None:
            return
        if not self.store.claim_message(msg.message_id, msg.chat_id):
            logger.info("忽略重复消息：%s", msg.message_id)
            return
        future = asyncio.run_coroutine_threadsafe(self.handle(msg), self.loop)
        future.add_done_callback(self._log_future_error)

    @staticmethod
    def _log_future_error(future) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("飞书消息处理出现未捕获异常")

    async def handle(self, msg: IncomingMessage) -> None:
        lock = self._chat_locks.setdefault(msg.chat_id, asyncio.Lock())
        async with lock:
            await self._handle_serial(msg)

    async def _handle_serial(self, msg: IncomingMessage) -> None:
        card = None
        try:
            if msg.msg_type in {"text", "post"} and NEW_CHAT_RE.fullmatch(
                re.sub(r"[\s~!！?？。.,，、]+", "", msg.text)
            ):
                self.store.reset_session(msg.chat_id)
                self.store.update_task(msg.message_id, None, "completed")
                await self._send(msg, "已开启全新对话，此前的上下文不再带入。请继续～")
                return

            prompt = await self._build_prompt(msg)
            if not prompt:
                return
            session_id = self.store.session_id(msg.chat_id)
            self.store.update_task(msg.message_id, None, "streaming")
            card = await asyncio.to_thread(self.feishu.create_streaming_card, msg)
            content = ""
            last_flushed = ""
            last_flush_at = time.monotonic()
            ack_task = asyncio.create_task(self._delayed_card_ack(card))
            try:
                async with asyncio.timeout(self.settings.task_timeout_seconds):
                    async for chunk in self.coze.stream(
                        prompt, session_id, self.settings.task_timeout_seconds
                    ):
                        if ack_task is not None:
                            ack_task.cancel()
                            ack_task = None
                        content = merge_stream_text(content, chunk)
                        now = time.monotonic()
                        should_flush = (
                            not last_flushed
                            or len(content) - len(last_flushed) >= 50
                            or now - last_flush_at >= 0.4
                        )
                        if should_flush:
                            await asyncio.to_thread(card.update, content)
                            last_flushed = content
                            last_flush_at = now
                if not content.strip():
                    raise CozeAPIError("Agent 流结束，但没有生成可回复内容")
                await asyncio.to_thread(card.finish, content)
                self.store.update_task(msg.message_id, None, "completed")
            except Exception as exc:
                try:
                    await asyncio.to_thread(card.fail, "连接中断，请稍后重试")
                except Exception:
                    logger.exception("流式卡片失败状态更新失败")
                raise
            finally:
                if ack_task is not None:
                    ack_task.cancel()
        except TimeoutError:
            self.store.update_task(msg.message_id, None, "timeout")
            logger.exception("扣子任务超时：message=%s", msg.message_id)
            if card is None:
                await self._send(msg, "处理超时了，任务可能过于复杂，请拆小后重试。")
        except (CozeAPIError, ValueError, RuntimeError) as exc:
            self.store.update_task(msg.message_id, None, "failed")
            logger.exception("消息处理失败：message=%s", msg.message_id)
            if card is None:
                await self._send(msg, f"处理失败：{exc}")
        except Exception:
            self.store.update_task(msg.message_id, None, "failed")
            logger.exception("消息处理发生未知异常：message=%s", msg.message_id)
            if card is None:
                await self._send(msg, "处理出错了，请稍后重试。")

    async def _build_prompt(self, msg: IncomingMessage) -> str:
        if msg.msg_type in {"text", "post"}:
            return msg.text
        if msg.msg_type == "file":
            data = await asyncio.to_thread(self.feishu.download_resource, msg, "file")
            text = await asyncio.to_thread(extract_file_text, data, msg.file_name)
            return f"用户发送了文件《{msg.file_name}》，内容如下：\n\n{text}"
        if msg.msg_type == "image":
            await self._send(msg, "当前连接器暂不支持把图片直接传给扣子，请发送文字或文档。")
            self.store.update_task(msg.message_id, None, "unsupported")
            return ""
        await self._send(msg, f"暂不支持「{msg.msg_type}」类型的消息。")
        self.store.update_task(msg.message_id, None, "unsupported")
        return ""

    async def _send(self, msg: IncomingMessage, text: str) -> None:
        try:
            await asyncio.to_thread(self.feishu.send_text, msg, text)
        except Exception:
            logger.exception("回复飞书消息失败：message=%s", msg.message_id)

    async def _delayed_card_ack(self, card) -> None:
        """60 秒仍无 Agent 文本时，只更新同一张卡片，不额外发送消息。"""
        try:
            await asyncio.sleep(self.settings.ack_delay_seconds)
            await asyncio.to_thread(card.update, "⏳ 收到，正在处理中，请稍候…")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("更新流式卡片处理中状态失败")

    async def run_async_loop(self) -> None:
        self.loop = asyncio.get_running_loop()
        logger.info("连接器异步任务循环已启动")
        await asyncio.Event().wait()

    async def close(self) -> None:
        await self.coze.close()
        self.store.close()


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    connector = Connector(settings)
    worker_loop = asyncio.new_event_loop()

    def run_worker() -> None:
        asyncio.set_event_loop(worker_loop)
        worker_loop.run_until_complete(connector.run_async_loop())

    worker = threading.Thread(target=run_worker, name="connector-worker", daemon=True)
    worker.start()
    while connector.loop is None:
        time.sleep(0.01)

    event_handler = connector.feishu.build_event_handler(connector.on_event)
    logger.info("飞书连接器启动，Agent 请求将发送到 %s", settings.coze_api_base_url)
    try:
        while True:
            try:
                connector.feishu.run_websocket(event_handler)
                logger.warning("飞书 WebSocket 意外结束，5 秒后重连")
            except Exception:
                logger.exception("飞书 WebSocket 断开，5 秒后重连")
            time.sleep(5)
    finally:
        future = asyncio.run_coroutine_threadsafe(connector.close(), worker_loop)
        try:
            future.result(timeout=10)
        except Exception:
            logger.exception("关闭连接器资源失败")
        worker_loop.call_soon_threadsafe(worker_loop.stop)


if __name__ == "__main__":
    main()
