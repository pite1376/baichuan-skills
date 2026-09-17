import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少必需环境变量 {name}")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"环境变量 {name} 必须是数字") from exc
    if value <= 0:
        raise RuntimeError(f"环境变量 {name} 必须大于 0")
    return value


@dataclass(frozen=True)
class Settings:
    feishu_app_id: str
    feishu_app_secret: str
    coze_api_token: str
    coze_project_id: int
    coze_api_base_url: str
    ack_delay_seconds: float
    task_timeout_seconds: float
    poll_interval_seconds: float
    request_timeout_seconds: float
    database_path: str
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        try:
            project_id = int(_required("COZE_PROJECT_ID"))
        except ValueError as exc:
            raise RuntimeError("环境变量 COZE_PROJECT_ID 必须是整数") from exc
        return cls(
            feishu_app_id=_required("FEISHU_APP_ID"),
            feishu_app_secret=_required("FEISHU_APP_SECRET"),
            coze_api_token=_required("COZE_API_TOKEN"),
            coze_project_id=project_id,
            coze_api_base_url=os.getenv(
                "COZE_API_BASE_URL", "https://76mwxwmfhb.coze.site"
            ).strip().rstrip("/"),
            ack_delay_seconds=_positive_float("ACK_DELAY_SECONDS", 15),
            task_timeout_seconds=_positive_float("TASK_TIMEOUT_SECONDS", 900),
            poll_interval_seconds=_positive_float("POLL_INTERVAL_SECONDS", 2),
            request_timeout_seconds=_positive_float("REQUEST_TIMEOUT_SECONDS", 30),
            database_path=os.getenv("CONNECTOR_DATABASE_PATH", "/app/data/connector.db"),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

