import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SessionResolution:
    session_id: str
    status: str
    generation: int


class Store:
    """单实例连接器持久化：消息去重、会话映射和群聊上下文游标。"""

    def __init__(self, path: str):
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(db_path)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
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
                CREATE TABLE IF NOT EXISTS conversation_sessions (
                    conversation_key TEXT PRIMARY KEY,
                    scope_type TEXT NOT NULL,
                    session_id TEXT NOT NULL UNIQUE,
                    generation INTEGER NOT NULL DEFAULT 0,
                    last_context_time INTEGER,
                    last_context_message_id TEXT,
                    created_at REAL NOT NULL,
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

    def legacy_session_id(
        self, chat_id: str, current_message_id: Optional[str] = None
    ) -> Optional[str]:
        """仅在数据库能证明该 chat 已被旧版处理时返回旧 session_id。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT sequence FROM sessions WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            if current_message_id:
                prior_message = self._conn.execute(
                    "SELECT 1 FROM messages WHERE chat_id = ? AND message_id <> ? LIMIT 1",
                    (chat_id, current_message_id),
                ).fetchone()
            else:
                prior_message = self._conn.execute(
                    "SELECT 1 FROM messages WHERE chat_id = ? LIMIT 1", (chat_id,)
                ).fetchone()
        if row is None and prior_message is None:
            return None
        sequence = int(row["sequence"]) if row else 0
        suffix = "" if sequence == 0 else f"_{sequence}"
        return f"feishu_{chat_id}{suffix}"

    def resolve_session(
        self,
        conversation_key: str,
        scope_type: str,
        legacy_session_id: Optional[str] = None,
    ) -> SessionResolution:
        """原子读取或创建会话映射，并返回创建/迁移状态。"""
        if not conversation_key:
            raise ValueError("conversation_key 不能为空")
        if scope_type not in {"user", "chat", "thread"}:
            raise ValueError(f"不支持的 scope_type：{scope_type}")

        now = time.time()
        candidate = legacy_session_id or str(uuid.uuid4())
        status = "migrated" if legacy_session_id else "created"
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                row = self._conn.execute(
                    "SELECT session_id, generation FROM conversation_sessions "
                    "WHERE conversation_key = ?",
                    (conversation_key,),
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO conversation_sessions "
                        "(conversation_key, scope_type, session_id, generation, "
                        "created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
                        (conversation_key, scope_type, candidate, now, now),
                    )
                    row = self._conn.execute(
                        "SELECT session_id, generation FROM conversation_sessions "
                        "WHERE conversation_key = ?",
                        (conversation_key,),
                    ).fetchone()
                else:
                    status = "existing"
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return SessionResolution(
            session_id=str(row["session_id"]),
            status=status,
            generation=int(row["generation"]),
        )

    def get_or_create_session(
        self,
        conversation_key: str,
        scope_type: str,
        legacy_session_id: Optional[str] = None,
    ) -> str:
        return self.resolve_session(
            conversation_key, scope_type, legacy_session_id
        ).session_id

    def reset_session(self, conversation_key: str, scope_type: str) -> str:
        if not conversation_key:
            raise ValueError("conversation_key 不能为空")
        now = time.time()
        new_session_id = str(uuid.uuid4())
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                row = self._conn.execute(
                    "SELECT generation FROM conversation_sessions "
                    "WHERE conversation_key = ?",
                    (conversation_key,),
                ).fetchone()
                if row is None:
                    self._conn.execute(
                        "INSERT INTO conversation_sessions "
                        "(conversation_key, scope_type, session_id, generation, "
                        "last_context_time, last_context_message_id, created_at, updated_at) "
                        "VALUES (?, ?, ?, 1, NULL, NULL, ?, ?)",
                        (conversation_key, scope_type, new_session_id, now, now),
                    )
                else:
                    self._conn.execute(
                        "UPDATE conversation_sessions SET session_id = ?, "
                        "generation = generation + 1, last_context_time = NULL, "
                        "last_context_message_id = NULL, updated_at = ? "
                        "WHERE conversation_key = ?",
                        (new_session_id, now, conversation_key),
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return new_session_id

    def get_context_cursor(
        self, conversation_key: str
    ) -> tuple[Optional[int], Optional[str]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT last_context_time, last_context_message_id "
                "FROM conversation_sessions WHERE conversation_key = ?",
                (conversation_key,),
            ).fetchone()
        if row is None:
            return None, None
        return row["last_context_time"], row["last_context_message_id"]

    def update_context_cursor(
        self, conversation_key: str, create_time: int, message_id: str
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE conversation_sessions SET last_context_time = ?, "
                "last_context_message_id = ?, updated_at = ? "
                "WHERE conversation_key = ?",
                (create_time, message_id, time.time(), conversation_key),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()
