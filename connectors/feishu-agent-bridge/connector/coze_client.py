import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"success", "succeeded", "completed", "complete", "done"}
FAILURE_STATUSES = {"failed", "failure", "error", "cancelled", "canceled", "timeout"}
RUNNING_STATUSES = {
    "created", "queued", "pending", "running", "processing", "in_progress"
}


class CozeAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    status: str
    text: str
    raw: dict[str, Any]


class CozeClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        project_id: int,
        request_timeout: float = 30,
    ):
        self.project_id = project_id
        self.request_timeout = request_timeout
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(request_timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _payload(self, text: str, session_id: str) -> dict[str, Any]:
        return {
            "content": {
                "query": {
                    "prompt": [
                        {"type": "text", "content": {"text": text}}
                    ]
                }
            },
            "type": "query",
            "session_id": session_id,
            "project_id": self.project_id,
        }

    async def submit(self, text: str, session_id: str) -> str:
        payload = self._payload(text, session_id)
        data = await self._request_json("POST", "/async_run", json=payload)
        task_id = _find_string(data, ("task_id", "taskId"))
        if not task_id and data.get("id") is not None:
            task_id = str(data["id"]).strip()
        if not task_id:
            raise CozeAPIError(f"扣子提交响应中没有 task_id：{_safe_json(data)}")
        return task_id

    async def stream(self, text: str, session_id: str, timeout: float):
        """调用 /stream_run 并产出 Agent 用户可见文本块。"""
        payload = self._payload(text, session_id)
        # run_id 每次请求唯一；LangGraph 的 AgentStreamRunner 会从 payload 中
        # 读取稳定 session_id 作为 thread_id，因此日志/取消与上下文互不混用。
        request_id = uuid.uuid4().hex
        headers = {"x-run-id": request_id, "x-request-id": request_id}
        try:
            async with self._client.stream(
                "POST",
                "/stream_run",
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=self.request_timeout,
                    read=timeout,
                    write=self.request_timeout,
                    pool=self.request_timeout,
                ),
            ) as response:
                if response.status_code in (401, 403):
                    raise CozeAPIError("扣子 API 鉴权失败，请检查 COZE_API_TOKEN")
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")[:1000]
                    raise CozeAPIError(
                        f"扣子流式 API 异常：HTTP {response.status_code} {body}"
                    )
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_lines.append(line[5:].lstrip())
                        continue
                    if line == "" and data_lines:
                        raw = "\n".join(data_lines)
                        data_lines.clear()
                        if raw == "[DONE]":
                            break
                        error = extract_stream_error(raw)
                        if error:
                            raise CozeAPIError(f"扣子流式任务失败：{error}")
                        chunk = extract_stream_text(raw)
                        if chunk:
                            yield chunk
                if data_lines:
                    chunk = extract_stream_text("\n".join(data_lines))
                    if chunk:
                        yield chunk
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise CozeAPIError(f"扣子 SSE 连接中断：{exc}") from exc

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request_json("GET", f"/task/{task_id}")

    async def wait_for_result(
        self, task_id: str, timeout: float, poll_interval: float
    ) -> TaskResult:
        deadline = time.monotonic() + timeout
        transient_failures = 0
        while time.monotonic() < deadline:
            try:
                data = await self.get_task(task_id)
                transient_failures = 0
            except (httpx.TransportError, httpx.TimeoutException, CozeAPIError) as exc:
                transient_failures += 1
                if transient_failures > 5:
                    raise
                delay = min(poll_interval * (2 ** (transient_failures - 1)), 15)
                logger.warning("查询任务 %s 暂时失败，%.1f 秒后重试：%s", task_id, delay, exc)
                await asyncio.sleep(delay)
                continue

            status = _extract_status(data)
            if status in SUCCESS_STATUSES:
                text = extract_reply_text(data)
                if not text:
                    raise CozeAPIError(
                        f"任务已完成，但响应中没有可回复文本：{_safe_json(data)}"
                    )
                return TaskResult(task_id=task_id, status=status, text=text, raw=data)
            if status in FAILURE_STATUSES:
                error = _find_string(data, ("error_message", "message", "error", "detail"))
                raise CozeAPIError(f"扣子任务失败（{status}）：{error or _safe_json(data)}")
            if status and status not in RUNNING_STATUSES:
                logger.warning("任务 %s 返回未知状态 %s，继续轮询", task_id, status)
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"扣子任务 {task_id} 超过 {timeout:g} 秒仍未完成")

    async def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self._client.request(method, path, **kwargs)
        if response.status_code in (401, 403):
            raise CozeAPIError("扣子 API 鉴权失败，请检查或轮换 COZE_API_TOKEN")
        if response.status_code == 429 or response.status_code >= 500:
            raise CozeAPIError(
                f"扣子 API 暂时不可用：HTTP {response.status_code}"
            )
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPStatusError, ValueError) as exc:
            body = response.text[:1000]
            raise CozeAPIError(
                f"扣子 API 响应异常：HTTP {response.status_code} {body}"
            ) from exc
        if not isinstance(data, dict):
            raise CozeAPIError(f"扣子 API 返回的不是 JSON 对象：{_safe_json(data)}")
        return data


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)[:2000]


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _find_string(value: Any, keys: tuple[str, ...]) -> Optional[str]:
    for obj in _walk(value):
        for key in keys:
            item = obj.get(key)
            if item is not None and not isinstance(item, (dict, list)):
                text = str(item).strip()
                if text:
                    return text
    return None


def _extract_status(data: dict[str, Any]) -> str:
    status = _find_string(data, ("task_status", "taskStatus", "status", "state"))
    return (status or "").strip().lower().replace("-", "_").replace(" ", "_")


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(part.strip() for part in parts if part.strip())
    return ""


def extract_reply_text(data: dict[str, Any]) -> str:
    """兼容常见异步任务及 LangChain messages 返回结构。"""
    messages: list[dict[str, Any]] = []
    for obj in _walk(data):
        value = obj.get("messages")
        if isinstance(value, list):
            messages.extend(item for item in value if isinstance(item, dict))
    for message in reversed(messages):
        role = str(message.get("role") or message.get("type") or "").lower()
        if role in {"assistant", "ai", "aimessage"} or not role:
            text = _content_to_text(message.get("content"))
            if text:
                return text

    for key in ("output_text", "answer", "reply", "text"):
        for obj in _walk(data):
            text = _content_to_text(obj.get(key))
            if text:
                return text

    for key in ("result", "output", "data"):
        value = data.get(key)
        text = _content_to_text(value)
        if text:
            return text
    return ""


def extract_stream_text(raw: str) -> str:
    """从常见 Chat/LangGraph SSE 事件中提取单个 AI 文本块。"""
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""

    if str(data.get("type") or "").lower() == "answer":
        content = data.get("content")
        if isinstance(content, dict):
            answer = content.get("answer")
            return answer if isinstance(answer, str) else ""

    choices = data.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict):
                text = _stream_content_to_text(delta.get("content"))
                if text:
                    return text

    candidates = [data]
    for key in ("data", "message", "chunk"):
        value = data.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    for item in candidates:
        kind = str(
            item.get("role") or item.get("type") or item.get("message_type") or ""
        ).lower()
        if (
            kind in {"assistant", "ai", "aimessage", "aimessagechunk", "answer"}
            or "ai_message" in kind
            or "chat.completion.chunk" in str(data.get("object", "")).lower()
        ):
            text = _stream_content_to_text(item.get("content"))
            if text:
                return text
    return ""


def _stream_content_to_text(content: Any) -> str:
    """流式文本不能 strip，否则空格和换行 token 会被吃掉。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def extract_stream_error(raw: str) -> str:
    try:
        data = json.loads(raw)
    except ValueError:
        return ""
    if not isinstance(data, dict) or str(data.get("type") or "").lower() != "error":
        return ""
    content = data.get("content")
    if isinstance(content, dict):
        error = content.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "未知错误")
        if error:
            return str(error)
    return "未知错误"


def merge_stream_text(current: str, incoming: str) -> str:
    """兼容增量 chunk 和累计快照，避免最终完整消息被重复追加。"""
    if not incoming:
        return current
    if incoming.startswith(current):
        return incoming
    if current.endswith(incoming):
        return current
    max_overlap = min(len(current), len(incoming))
    for size in range(max_overlap, 0, -1):
        if current[-size:] == incoming[:size]:
            return current + incoming[size:]
    return current + incoming
