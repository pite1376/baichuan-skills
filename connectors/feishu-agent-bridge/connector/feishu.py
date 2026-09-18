import asyncio
import json
import logging
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import lark_oapi as lark
from lark_oapi.channel.bot_identity import fetch_bot_identity
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
    ListMessageRequest,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)
from lark_oapi.api.cardkit.v1 import (
    ContentCardElementRequest,
    ContentCardElementRequestBody,
    CreateCardRequest,
    CreateCardRequestBody,
    SettingsCardRequest,
    SettingsCardRequestBody,
)

logger = logging.getLogger(__name__)
_MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
_MENTION_TOKEN_RE = re.compile(r"@_user_\d+")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_BLOCK_LINE_RE = re.compile(
    r"^\s*(?:#{1,6}\s|>|[-+*]\s|\d+[.)]\s|"
    r"(?:-{3,}|_{3,}|\*{3,})\s*$|<hr\b)",
    re.IGNORECASE,
)
_TABLE_DIVIDER_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


class CardOperationError(RuntimeError):
    def __init__(self, stage: str, code: object, message: object):
        self.stage = stage
        self.code = code
        self.api_message = str(message or "")
        super().__init__(
            f"飞书流式卡片 {stage} 失败：code={code} msg={self.api_message}"
        )


@dataclass(frozen=True)
class MentionInfo:
    key: str
    open_id: str
    mentioned_type: str
    name: str


@dataclass(frozen=True)
class IncomingMessage:
    message_id: str
    chat_id: str
    chat_type: str
    msg_type: str
    text: str = ""
    file_key: str = ""
    file_name: str = ""
    sender_open_id: str = ""
    sender_type: str = ""
    thread_id: str = ""
    root_id: str = ""
    create_time: int = 0
    mentions: tuple[MentionInfo, ...] = ()
    bot_mentioned: bool = False

    @property
    def is_group(self) -> bool:
        return self.chat_type != "p2p"

    @property
    def is_thread(self) -> bool:
        return bool(self.thread_id or self.root_id)

    @property
    def thread_key(self) -> str:
        return self.thread_id or self.root_id


@dataclass(frozen=True)
class GroupContextMessage:
    message_id: str
    create_time: int
    sender_name: str
    sender_id: str
    text: str
    thread_id: str = ""
    root_id: str = ""


def _streaming_card_spec() -> dict:
    """最小化流式卡片：不展示机器人品牌或永久生成状态。"""
    return {
        "schema": "2.0",
        "config": {
            "update_multi": True,
            "width_mode": "default",
            "streaming_mode": True,
            "enable_forward": True,
        },
        "body": {
            "direction": "vertical",
            "padding": "12px 12px 20px 12px",
            "elements": [
                {
                    "tag": "markdown",
                    "element_id": "stream_md",
                    "content": "正在连接智能体，请稍候…",
                }
            ],
        },
    }


def format_card_markdown(text: str) -> str:
    """让普通正文的单换行稳定显示，同时保护 Markdown 块级结构。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if len(lines) < 2:
        return normalized

    output: list[str] = []
    in_fence = False
    fence_char = ""
    fence_size = 0
    for index, line in enumerate(lines):
        output.append(line)
        if index == len(lines) - 1:
            break

        fence = _FENCE_RE.match(line)
        was_in_fence = in_fence
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_size = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_size:
                in_fence = False
                fence_char = ""
                fence_size = 0

        next_line = lines[index + 1]
        if (
            was_in_fence
            or in_fence
            or not line
            or not next_line
            or _is_markdown_block_line(line)
            or _is_markdown_block_line(next_line)
            or re.search(r"(?:<br\s*/?>| {2,})\s*$", line, re.IGNORECASE)
        ):
            output.append("\n")
        else:
            output.append("<br>\n")
    return "".join(output)


def _is_markdown_block_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if line.startswith(("    ", "\t")):
        return True
    if _FENCE_RE.match(line) or _BLOCK_LINE_RE.match(line) or _TABLE_DIVIDER_RE.match(line):
        return True
    # 表格行保持原始换行；保守处理任意包含竖线的行，避免破坏列结构。
    return "|" in stripped


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        self.bot_open_id = ""

    def resolve_bot_identity(self) -> bool:
        identity = asyncio.run(fetch_bot_identity(self.client.config))
        if identity is None or not identity.open_id:
            return False
        self.bot_open_id = identity.open_id
        logger.info("飞书机器人身份解析成功：name=%s", identity.name or "unknown")
        return True

    def send_text(self, msg: IncomingMessage, text: str) -> None:
        for chunk in _chunk_text(text):
            use_post = bool(_MD_LINK_RE.search(chunk))
            msg_type = "post" if use_post else "text"
            content_obj = _to_post(chunk) if use_post else {"text": chunk}
            content = json.dumps(content_obj, ensure_ascii=False)
            if not msg.is_group:
                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type("chat_id")
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(msg.chat_id)
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self.client.im.v1.message.create(request)
            else:
                body = (
                    ReplyMessageRequestBody.builder()
                    .msg_type(msg_type)
                    .content(content)
                    .reply_in_thread(msg.is_thread)
                    .build()
                )
                request = (
                    ReplyMessageRequest.builder()
                    .message_id(msg.message_id)
                    .request_body(body)
                    .build()
                )
                response = self.client.im.v1.message.reply(request)
            if not response.success():
                raise RuntimeError(
                    f"飞书发送失败：code={response.code} msg={response.msg}"
                )

    def create_streaming_card(self, msg: IncomingMessage) -> "StreamingCard":
        """创建并发送 CardKit 2.0 流式卡片，返回可持续更新的控制器。"""
        spec = _streaming_card_spec()
        create_request = (
            CreateCardRequest.builder()
            .request_body(
                CreateCardRequestBody.builder()
                .type("card_json")
                .data(json.dumps(spec, ensure_ascii=False))
                .build()
            )
            .build()
        )
        create_response = self.client.cardkit.v1.card.create(create_request)
        card_id = getattr(getattr(create_response, "data", None), "card_id", "")
        if not create_response.success() or not card_id:
            raise CardOperationError(
                "create", create_response.code, create_response.msg
            )

        card_content = json.dumps(
            {"type": "card", "data": {"card_id": card_id}}, ensure_ascii=False
        )
        if not msg.is_group:
            send_request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(msg.chat_id)
                    .msg_type("interactive")
                    .content(card_content)
                    .build()
                )
                .build()
            )
            send_response = self.client.im.v1.message.create(send_request)
        else:
            body = (
                ReplyMessageRequestBody.builder()
                .msg_type("interactive")
                .content(card_content)
                .reply_in_thread(msg.is_thread)
                .build()
            )
            send_request = (
                ReplyMessageRequest.builder()
                .message_id(msg.message_id)
                .request_body(body)
                .build()
            )
            send_response = self.client.im.v1.message.reply(send_request)
        if not send_response.success():
            raise CardOperationError("send", send_response.code, send_response.msg)
        message_id = getattr(getattr(send_response, "data", None), "message_id", "")
        return StreamingCard(self, card_id, message_id)

    def update_streaming_card(
        self, card_id: str, content: str, sequence: int
    ) -> None:
        request = (
            ContentCardElementRequest.builder()
            .card_id(card_id)
            .element_id("stream_md")
            .request_body(
                ContentCardElementRequestBody.builder()
                .content(format_card_markdown(content or "…"))
                .sequence(sequence)
                .build()
            )
            .build()
        )
        response = self.client.cardkit.v1.card_element.content(request)
        if not response.success():
            raise CardOperationError("update", response.code, response.msg)

    def finish_streaming_card(self, card_id: str, sequence: int) -> None:
        request = (
            SettingsCardRequest.builder()
            .card_id(card_id)
            .request_body(
                SettingsCardRequestBody.builder()
                .settings(json.dumps({"config": {"streaming_mode": False}}))
                .sequence(sequence)
                .build()
            )
            .build()
        )
        response = self.client.cardkit.v1.card.settings(request)
        if not response.success():
            raise CardOperationError("finish", response.code, response.msg)

    def list_recent_group_messages(
        self,
        msg: IncomingMessage,
        max_messages: int,
        window_seconds: int,
        after_time: Optional[int] = None,
        after_message_id: Optional[str] = None,
    ) -> list[GroupContextMessage]:
        now = int(time.time())
        request = (
            ListMessageRequest.builder()
            .container_id_type("chat")
            .container_id(msg.chat_id)
            .start_time(str(now - window_seconds))
            .end_time(str(now))
            .sort_type("ByCreateTimeDesc")
            .page_size(min(max(max_messages, 1), 50))
            .with_sender_name(True)
            .build()
        )
        response = self.client.im.v1.message.list(request)
        if not response.success():
            raise RuntimeError(
                f"飞书群消息读取失败：code={response.code} msg={response.msg}"
            )

        result: list[GroupContextMessage] = []
        current_thread = msg.thread_key
        for item in getattr(getattr(response, "data", None), "items", None) or []:
            if getattr(item, "deleted", False):
                continue
            if item.message_id == msg.message_id:
                continue
            if item.msg_type not in {"text", "post"}:
                continue
            sender = getattr(item, "sender", None)
            sender_type = str(getattr(sender, "sender_type", "") or "").lower()
            if sender_type in {"app", "bot"}:
                continue

            item_thread = str(getattr(item, "thread_id", "") or "")
            item_root = str(getattr(item, "root_id", "") or "")
            item_thread_key = item_thread or item_root
            if current_thread:
                if item_thread_key != current_thread:
                    continue
            elif item_thread_key:
                continue

            create_time = _timestamp_seconds(getattr(item, "create_time", 0))
            cursor = (after_time or 0, after_message_id or "")
            if after_time is not None and (create_time, item.message_id or "") <= cursor:
                continue

            try:
                body = json.loads(getattr(getattr(item, "body", None), "content", "{}") or "{}")
            except ValueError:
                continue
            if item.msg_type == "text":
                text = str(body.get("text") or "").strip()
            else:
                text = _parse_post_text(body)
            text = _render_mentions(text, getattr(item, "mentions", None) or [])
            if not text:
                continue
            sender_id = str(getattr(sender, "id", "") or "")
            sender_name = str(getattr(sender, "sender_name", "") or "").strip()
            result.append(
                GroupContextMessage(
                    message_id=str(item.message_id or ""),
                    create_time=create_time,
                    sender_name=sender_name,
                    sender_id=sender_id,
                    text=text,
                    thread_id=item_thread,
                    root_id=item_root,
                )
            )
        result.sort(key=lambda item: (item.create_time, item.message_id))
        return result[-max_messages:]

    def download_resource(self, msg: IncomingMessage, resource_type: str) -> bytes:
        request = (
            GetMessageResourceRequest.builder()
            .message_id(msg.message_id)
            .file_key(msg.file_key)
            .type(resource_type)
            .build()
        )
        response = self.client.im.v1.message_resource.get(request)
        if not response.success():
            raise RuntimeError(
                f"飞书资源下载失败：code={response.code} msg={response.msg}"
            )
        return response.file.read()

    def build_event_handler(self, callback):
        return (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(callback)
            .build()
        )

    def run_websocket(self, event_handler) -> None:
        ws_client = lark.ws.Client(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )
        ws_client.start()


class StreamingCard:
    """单元素 CardKit 流式卡片；调用方负责节流，sequence 在此严格递增。"""

    def __init__(self, client: FeishuClient, card_id: str, message_id: str = ""):
        self.client = client
        self.card_id = card_id
        self.message_id = message_id
        self.sequence = 0
        self.content = ""
        self.finished = False
        self._lock = threading.RLock()

    def update(self, content: str) -> None:
        with self._lock:
            if self.finished:
                return
            self.sequence += 1
            self.client.update_streaming_card(self.card_id, content, self.sequence)
            self.content = content

    def finish(self, content: Optional[str] = None) -> None:
        with self._lock:
            if self.finished:
                return
            if content is not None and content != self.content:
                self.update(content)
            self.sequence += 1
            self.client.finish_streaming_card(self.card_id, self.sequence)
            self.finished = True

    def fail(self, message: str) -> None:
        footer = f"\n\n---\n生成中断：{message}"
        self.finish((self.content or "暂未生成内容") + footer)


def parse_event(
    data: P2ImMessageReceiveV1, bot_open_id: str = ""
) -> Optional[IncomingMessage]:
    event = getattr(data, "event", None)
    message = getattr(event, "message", None)
    sender = getattr(event, "sender", None)
    if message is None:
        return None
    sender_type = str(getattr(sender, "sender_type", "") or "")
    if sender_type.lower() in {"app", "bot"}:
        return None
    sender_id = getattr(sender, "sender_id", None)
    sender_open_id = str(getattr(sender_id, "open_id", "") or "")
    try:
        content = json.loads(message.content or "{}")
    except ValueError:
        logger.exception("无法解析飞书消息 %s", message.message_id)
        return None

    mentions = tuple(
        MentionInfo(
            key=str(getattr(item, "key", "") or ""),
            open_id=str(getattr(getattr(item, "id", None), "open_id", "") or ""),
            mentioned_type=str(getattr(item, "mentioned_type", "") or ""),
            name=str(getattr(item, "name", "") or ""),
        )
        for item in (getattr(message, "mentions", None) or [])
    )
    bot_mentions = tuple(
        item for item in mentions if bot_open_id and item.open_id == bot_open_id
    )
    common = {
        "message_id": str(message.message_id or ""),
        "chat_id": str(message.chat_id or ""),
        "chat_type": str(message.chat_type or ""),
        "msg_type": str(message.message_type or ""),
        "sender_open_id": sender_open_id,
        "sender_type": sender_type,
        "thread_id": str(getattr(message, "thread_id", "") or ""),
        "root_id": str(getattr(message, "root_id", "") or ""),
        "create_time": _timestamp_seconds(getattr(message, "create_time", 0)),
        "mentions": mentions,
        "bot_mentioned": bool(bot_mentions),
    }
    if message.message_type == "text":
        text = str(content.get("text") or "").strip()
        for mention in bot_mentions:
            if mention.key:
                text = text.replace(mention.key, "", 1).strip()
        text = _MENTION_TOKEN_RE.sub("", text, count=1).strip()
        return IncomingMessage(**common, text=text) if text else None
    if message.message_type == "post":
        text = _parse_post_text(content)
        for mention in bot_mentions:
            if mention.name:
                text = text.replace(f"@{mention.name}", "", 1).strip()
        return IncomingMessage(**common, text=text) if text else None
    if message.message_type == "file":
        key = content.get("file_key", "")
        return (
            IncomingMessage(
                **common,
                file_key=key,
                file_name=content.get("file_name", "未知文件"),
            )
            if key
            else None
        )
    if message.message_type == "image":
        key = content.get("image_key", "")
        return IncomingMessage(**common, file_key=key) if key else None
    return IncomingMessage(**common)


def extract_file_text(data: bytes, file_name: str, max_chars: int = 20000) -> str:
    suffix = Path(file_name).suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json"}:
        text = data.decode("utf-8", errors="replace")
    elif suffix == ".pdf":
        from pypdf import PdfReader

        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            handle.write(data)
            handle.flush()
            text = "\n".join(
                page.extract_text() or "" for page in PdfReader(handle.name).pages
            )
    elif suffix == ".docx":
        from docx import Document

        with tempfile.NamedTemporaryFile(suffix=".docx") as handle:
            handle.write(data)
            handle.flush()
            text = "\n".join(
                p.text for p in Document(handle.name).paragraphs if p.text.strip()
            )
    else:
        raise ValueError("目前只支持 PDF、Word、TXT、MD、CSV 和 JSON 文件")
    text = text.strip()
    return text if len(text) <= max_chars else text[:max_chars] + "\n…（文件内容过长，已截断）"


def _timestamp_seconds(value: object) -> int:
    try:
        timestamp = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return timestamp // 1000 if timestamp > 10_000_000_000 else timestamp


def _chunk_text(text: str, limit: int = 3000) -> list[str]:
    if not text:
        return []
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _to_post(text: str) -> dict:
    lines = []
    for line in text.splitlines() or [""]:
        segments, last = [], 0
        for match in _MD_LINK_RE.finditer(line):
            if match.start() > last:
                segments.append({"tag": "text", "text": line[last : match.start()]})
            segments.append(
                {"tag": "a", "text": match.group(1), "href": match.group(2)}
            )
            last = match.end()
        if last < len(line):
            segments.append({"tag": "text", "text": line[last:]})
        lines.append(segments or [{"tag": "text", "text": ""}])
    return {"zh_cn": {"title": "", "content": lines}}


def _parse_post_text(content: dict) -> str:
    container = content
    if not isinstance(container.get("content"), list):
        for value in container.values():
            if isinstance(value, dict) and isinstance(value.get("content"), list):
                container = value
                break
    texts: list[str] = []
    for row in container.get("content", []) or []:
        for item in row or []:
            if item.get("tag") in {"text", "a", "at"}:
                value = item.get("text") or item.get("user_name") or ""
                if item.get("tag") == "at" and value:
                    value = f"@{value}"
                texts.append(value)
    return " ".join(filter(None, texts)).strip()


def _render_mentions(text: str, mentions: list[object]) -> str:
    for mention in mentions:
        key = str(getattr(mention, "key", "") or "")
        name = str(getattr(mention, "name", "") or "")
        if key:
            text = text.replace(key, f"@{name}" if name else "")
    return text.strip()
