import asyncio
import json
import logging
import time
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

    async def submit(self, text: str, session_id: str) -> str:
        payload = {
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
        data = await self._request_json("POST", "/async_run", json=payload)
        task_id = _find_string(data, ("task_id", "taskId"))
        if not task_id and data.get("id") is not None:
            task_id = str(data["id"]).strip()
        if not task_id:
            raise CozeAPIError(f"扣子提交响应中没有 task_id：{_safe_json(data)}")
        return task_id

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
