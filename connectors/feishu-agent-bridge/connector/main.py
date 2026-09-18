import asyncio
import hashlib
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import certifi

# 部分精简系统镜像或本地 Python 没有完整 CA 路径，显式使用 certifi；
# 仍然执行正常 TLS 证书校验，不会关闭 HTTPS/WSS 安全检查。
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from connector import __version__
from connector.coze_client import CozeAPIError, CozeClient, merge_stream_text
from connector.feishu import (
    CardOperationError,
    FeishuClient,
    GroupContextMessage,
    IncomingMessage,
    extract_file_text,
    parse_event,
)
from connector.settings import Settings
from connector.store import Store

logger = logging.getLogger(__name__)
NEW_CHAT_RE = re.compile(
    r"^(新建对话|新对话|开始新对话|开启新对话|重新对话|重置对话|"
    r"清空上下文|清除上下文|重新开始|reset|newchat|newconversation)$",
    re.IGNORECASE,
)
_SHANGHAI_TZ = timezone(timedelta(hours=8))


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12] if value else "missing"


def resolve_conversation(msg: IncomingMessage) -> tuple[str, str]:
    if not msg.is_group:
        if not msg.sender_open_id:
            raise ValueError("飞书私聊事件缺少发送者 open_id，已拒绝创建共享会话")
        return f"user:{msg.sender_open_id}", "user"
    if msg.thread_key:
        return f"thread:{msg.chat_id}:{msg.thread_key}", "thread"
    return f"chat:{msg.chat_id}", "chat"


def build_group_prompt(
    current_prompt: str,
    messages: list[GroupContextMessage],
    max_chars: int,
) -> tuple[str, int]:
    if not messages:
        return current_prompt, 0

    candidates: list[str] = []
    for item in messages:
        timestamp = datetime.fromtimestamp(
            item.create_time or 0, _SHANGHAI_TZ
        ).strftime("%m-%d %H:%M")
        sender = item.sender_name.strip() or f"用户-{_fingerprint(item.sender_id)}"
        text = item.text.strip()[:1000]
        if text:
            candidates.append(f"[{timestamp}] {sender}：{text}")

    selected: list[str] = []
    used = 0
    for line in reversed(candidates):
        cost = len(line) + (2 if selected else 0)
        if used + cost > max_chars:
            continue
        selected.append(line)
        used += cost
    selected.reverse()
    if not selected:
        return current_prompt, 0

    context = "\n\n".join(selected)
    prompt = (
        "以下是当前飞书群聊或话题最近的对话背景，仅用于理解当前问题：\n\n"
        f"{context}\n\n"
        "当前明确向机器人提出的问题：\n"
        f"{current_prompt}"
    )
    return prompt, len(context)


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
        self._conversation_locks: dict[str, asyncio.Lock] = {}

    def on_event(self, data) -> None:
        msg = parse_event(data, self.feishu.bot_open_id)
        if msg is None or self.loop is None:
            return
        if msg.is_group and not msg.bot_mentioned:
            logger.debug("忽略未 @机器人的群消息：message=%s", msg.message_id)
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
        try:
            conversation_key, _ = resolve_conversation(msg)
        except ValueError as exc:
            self.store.update_task(msg.message_id, None, "failed")
            logger.error("拒绝处理消息：message=%s reason=%s", msg.message_id, exc)
            await self._send(msg, f"处理失败：{exc}")
            return
        lock = self._conversation_locks.setdefault(conversation_key, asyncio.Lock())
        async with lock:
            await self._handle_serial(msg, conversation_key)

    async def _handle_serial(
        self, msg: IncomingMessage, conversation_key: str
    ) -> None:
        scope_type = resolve_conversation(msg)[1]
        card = None
        card_usable = False
        ack_task: Optional[asyncio.Task] = None
        session_id = ""
        started_at = time.monotonic()
        chunk_count = 0
        first_chunk_at: Optional[float] = None
        history_loaded = False
        history_count = 0
        history_chars = 0
        fallback_stage = ""

        try:
            if msg.msg_type in {"text", "post"} and NEW_CHAT_RE.fullmatch(
                re.sub(r"[\s~!！?？。.,，、]+", "", msg.text)
            ):
                self.store.reset_session(conversation_key, scope_type)
                self.store.update_task(msg.message_id, None, "completed")
                await self._send(msg, "已开启全新对话，此前的上下文不再带入。请继续～")
                logger.info(
                    "会话已重置：message=%s scope=%s conversation=%s",
                    msg.message_id,
                    scope_type,
                    _fingerprint(conversation_key),
                )
                return

            base_prompt = await self._build_prompt(msg)
            if not base_prompt:
                return

            legacy_session_id = (
                None
                if scope_type == "thread"
                else self.store.legacy_session_id(msg.chat_id, msg.message_id)
            )
            resolution = self.store.resolve_session(
                conversation_key, scope_type, legacy_session_id
            )
            session_id = resolution.session_id
            prompt = base_prompt

            if msg.is_group and self.settings.group_context_enabled:
                after_time, after_message_id = self.store.get_context_cursor(
                    conversation_key
                )
                try:
                    history = await asyncio.to_thread(
                        self.feishu.list_recent_group_messages,
                        msg,
                        self.settings.group_context_max_messages,
                        self.settings.group_context_window_seconds,
                        after_time,
                        after_message_id,
                    )
                    history_loaded = True
                    history_count = len(history)
                    prompt, history_chars = build_group_prompt(
                        base_prompt, history, self.settings.group_context_max_chars
                    )
                except Exception:
                    logger.exception(
                        "读取群聊近况失败，继续处理当前消息：message=%s", msg.message_id
                    )

            logger.info(
                "开始处理：message=%s scope=%s user=%s chat=%s thread=%s "
                "conversation=%s session=%s session_status=%s generation=%d "
                "history_count=%d history_chars=%d",
                msg.message_id,
                scope_type,
                _fingerprint(msg.sender_open_id),
                _fingerprint(msg.chat_id),
                _fingerprint(msg.thread_key),
                _fingerprint(conversation_key),
                _fingerprint(session_id),
                resolution.status,
                resolution.generation,
                history_count,
                history_chars,
            )

            self.store.update_task(msg.message_id, None, "streaming")
            try:
                card = await asyncio.to_thread(self.feishu.create_streaming_card, msg)
                card_usable = True
                ack_task = asyncio.create_task(self._delayed_card_ack(card))
                logger.info(
                    "CardKit 发送成功：message=%s card=%s card_message=%s",
                    msg.message_id,
                    _fingerprint(card.card_id),
                    _fingerprint(card.message_id),
                )
            except CardOperationError as exc:
                fallback_stage = exc.stage
                logger.warning(
                    "CardKit %s 失败，将降级为普通文本：message=%s code=%s msg=%s",
                    exc.stage,
                    msg.message_id,
                    exc.code,
                    exc.api_message,
                )
            except Exception:
                fallback_stage = "create_or_send"
                logger.exception(
                    "CardKit 创建或发送异常，将降级为普通文本：message=%s",
                    msg.message_id,
                )

            content = ""
            last_flushed = ""
            last_flush_at = time.monotonic()
            async with asyncio.timeout(self.settings.task_timeout_seconds):
                async for chunk in self.coze.stream(
                    prompt, session_id, self.settings.task_timeout_seconds
                ):
                    chunk_count += 1
                    if first_chunk_at is None:
                        first_chunk_at = time.monotonic()
                    if ack_task is not None:
                        ack_task.cancel()
                        ack_task = None
                    content = merge_stream_text(content, chunk)
                    if not card_usable:
                        continue
                    now = time.monotonic()
                    should_flush = (
                        not last_flushed
                        or len(content) - len(last_flushed) >= 50
                        or now - last_flush_at >= 0.4
                    )
                    if not should_flush:
                        continue
                    try:
                        await asyncio.to_thread(card.update, content)
                        last_flushed = content
                        last_flush_at = now
                    except CardOperationError as exc:
                        card_usable = False
                        fallback_stage = exc.stage
                        logger.warning(
                            "CardKit 更新失败，继续消费 SSE 并降级普通文本："
                            "message=%s code=%s msg=%s",
                            msg.message_id,
                            exc.code,
                            exc.api_message,
                        )
                    except Exception:
                        card_usable = False
                        fallback_stage = "update"
                        logger.exception(
                            "CardKit 更新异常，继续消费 SSE 并降级普通文本：message=%s",
                            msg.message_id,
                        )

            if not content.strip():
                raise CozeAPIError("Agent 流结束，但没有生成可回复内容")

            if card_usable:
                try:
                    await asyncio.to_thread(card.finish, content)
                except CardOperationError as exc:
                    card_usable = False
                    fallback_stage = exc.stage
                    logger.warning(
                        "CardKit 结束失败，将发送完整普通文本："
                        "message=%s code=%s msg=%s",
                        msg.message_id,
                        exc.code,
                        exc.api_message,
                    )
                except Exception:
                    card_usable = False
                    fallback_stage = "finish"
                    logger.exception(
                        "CardKit 结束异常，将发送完整普通文本：message=%s",
                        msg.message_id,
                    )
            if not card_usable:
                await self._send(msg, content)

            if msg.is_group and history_loaded:
                self.store.update_context_cursor(
                    conversation_key,
                    msg.create_time or int(time.time()),
                    msg.message_id,
                )
            self.store.update_task(msg.message_id, None, "completed")
            elapsed = time.monotonic() - started_at
            first_delay = (
                first_chunk_at - started_at if first_chunk_at is not None else -1
            )
            logger.info(
                "处理完成：message=%s session=%s first_chunk_seconds=%.3f "
                "total_seconds=%.3f chunks=%d chars=%d fallback=%s",
                msg.message_id,
                _fingerprint(session_id),
                first_delay,
                elapsed,
                chunk_count,
                len(content),
                fallback_stage or "none",
            )
        except TimeoutError:
            self.store.update_task(msg.message_id, None, "timeout")
            logger.exception("扣子任务超时：message=%s", msg.message_id)
            await self._report_stream_failure(
                msg, card if card_usable else None, "处理超时，请稍后重试。"
            )
        except (CozeAPIError, ValueError, RuntimeError) as exc:
            self.store.update_task(msg.message_id, None, "failed")
            logger.exception("消息处理失败：message=%s", msg.message_id)
            await self._report_stream_failure(
                msg, card if card_usable else None, f"处理失败：{exc}"
            )
        except Exception:
            self.store.update_task(msg.message_id, None, "failed")
            logger.exception("消息处理发生未知异常：message=%s", msg.message_id)
            await self._report_stream_failure(
                msg, card if card_usable else None, "处理出错了，请稍后重试。"
            )
        finally:
            if ack_task is not None:
                ack_task.cancel()
                await asyncio.gather(ack_task, return_exceptions=True)

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

    async def _report_stream_failure(
        self, msg: IncomingMessage, card, message: str
    ) -> None:
        if card is not None:
            try:
                await asyncio.to_thread(card.fail, message)
                return
            except Exception:
                logger.exception("流式卡片失败状态更新失败：message=%s", msg.message_id)
        await self._send(msg, message)

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
    try:
        if not connector.feishu.resolve_bot_identity():
            logger.warning("飞书机器人身份暂未解析，群聊 @ 检测将在重连时重试")
    except Exception:
        logger.exception("飞书机器人身份解析失败，私聊不受影响")
    worker_loop = asyncio.new_event_loop()

    def run_worker() -> None:
        asyncio.set_event_loop(worker_loop)
        worker_loop.run_until_complete(connector.run_async_loop())

    worker = threading.Thread(target=run_worker, name="connector-worker", daemon=True)
    worker.start()
    while connector.loop is None:
        time.sleep(0.01)

    event_handler = connector.feishu.build_event_handler(connector.on_event)
    logger.info(
        "飞书连接器启动：version=%s database=%s agent=%s group_context=%s",
        __version__,
        settings.database_path,
        settings.coze_api_base_url,
        settings.group_context_enabled,
    )
    try:
        while True:
            try:
                if not connector.feishu.bot_open_id:
                    try:
                        connector.feishu.resolve_bot_identity()
                    except Exception:
                        logger.exception("重试解析飞书机器人身份失败")
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
