import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional


class Store:
    """单实例连接器的轻量持久化：消息去重、任务映射和会话序号。"""

    def __init__(self, path: str):
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock, self._conn:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    task_id TEXT,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    chat_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                """
            )

    def claim_message(self, message_id: str, chat_id: str) -> bool:
        now = time.time()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO messages "
                "(message_id, chat_id, status, created_at, updated_at) "
                "VALUES (?, ?, 'received', ?, ?)",
                (message_id, chat_id, now, now),
            )
            return cursor.rowcount == 1

    def update_task(self, message_id: str, task_id: Optional[str], status: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE messages SET task_id = COALESCE(?, task_id), status = ?, "
                "updated_at = ? WHERE message_id = ?",
                (task_id, status, time.time(), message_id),
            )

    def session_id(self, chat_id: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT sequence FROM sessions WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        sequence = int(row["sequence"]) if row else 0
        suffix = "" if sequence == 0 else f"_{sequence}"
        return f"feishu_{chat_id}{suffix}"

    def reset_session(self, chat_id: str) -> str:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (chat_id, sequence, updated_at) VALUES (?, 1, ?) "
                "ON CONFLICT(chat_id) DO UPDATE SET "
                "sequence = sequence + 1, updated_at = excluded.updated_at",
                (chat_id, now),
            )
        return self.session_id(chat_id)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

