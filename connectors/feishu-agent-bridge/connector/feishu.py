import asyncio
import json
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    GetMessageResourceRequest,
    P2ImMessageReceiveV1,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

logger = logging.getLogger(__name__)
_MD_LINK_RE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")


@dataclass(frozen=True)
class IncomingMessage:
    message_id: str
    chat_id: str
    chat_type: str
    msg_type: str
    text: str = ""
    file_key: str = ""
    file_name: str = ""


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    def send_text(self, msg: IncomingMessage, text: str) -> None:
        for chunk in _chunk_text(text):
            use_post = bool(_MD_LINK_RE.search(chunk))
            msg_type = "post" if use_post else "text"
            content_obj = _to_post(chunk) if use_post else {"text": chunk}
            content = json.dumps(content_obj, ensure_ascii=False)
            if msg.chat_type == "p2p":
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
                request = (
                    ReplyMessageRequest.builder()
                    .message_id(msg.message_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self.client.im.v1.message.reply(request)
            if not response.success():
                raise RuntimeError(
                    f"飞书发送失败：code={response.code} msg={response.msg}"
                )

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


def parse_event(data: P2ImMessageReceiveV1) -> Optional[IncomingMessage]:
    message = data.event.message
    try:
        content = json.loads(message.content or "{}")
    except ValueError:
        logger.exception("无法解析飞书消息 %s", message.message_id)
        return None
    common = {
        "message_id": message.message_id,
        "chat_id": message.chat_id,
        "chat_type": message.chat_type,
        "msg_type": message.message_type,
    }
    if message.message_type == "text":
        text = (content.get("text") or "").strip()
        text = re.sub(r"^@_user_\d+\s*", "", text).strip()
        return IncomingMessage(**common, text=text) if text else None
    if message.message_type == "post":
        text = _parse_post_text(content)
        return IncomingMessage(**common, text=text) if text else None
    if message.message_type == "file":
        key = content.get("file_key", "")
        return IncomingMessage(
            **common, file_key=key, file_name=content.get("file_name", "未知文件")
        ) if key else None
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
            text = "\n".join(page.extract_text() or "" for page in PdfReader(handle.name).pages)
    elif suffix == ".docx":
        from docx import Document
        with tempfile.NamedTemporaryFile(suffix=".docx") as handle:
            handle.write(data)
            handle.flush()
            text = "\n".join(p.text for p in Document(handle.name).paragraphs if p.text.strip())
    else:
        raise ValueError("目前只支持 PDF、Word、TXT、MD、CSV 和 JSON 文件")
    text = text.strip()
    return text if len(text) <= max_chars else text[:max_chars] + "\n…（文件内容过长，已截断）"


def _chunk_text(text: str, limit: int = 3000) -> list[str]:
    if not text:
        return []
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def _to_post(text: str) -> dict:
    lines = []
    for line in text.splitlines() or [""]:
        segments, last = [], 0
        for match in _MD_LINK_RE.finditer(line):
            if match.start() > last:
                segments.append({"tag": "text", "text": line[last:match.start()]})
            segments.append({"tag": "a", "text": match.group(1), "href": match.group(2)})
            last = match.end()
        if last < len(line):
            segments.append({"tag": "text", "text": line[last:]})
        lines.append(segments or [{"tag": "text", "text": ""}])
    return {"zh_cn": {"title": "", "content": lines}}


def _parse_post_text(content: dict) -> str:
    texts = []
    for row in content.get("content", []) or []:
        for item in row or []:
            if item.get("tag") in {"text", "a"}:
                texts.append(item.get("text", ""))
    return " ".join(filter(None, texts)).strip()

