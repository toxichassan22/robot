from __future__ import annotations

import asyncio
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Literal

Role = Literal["user", "assistant", "system"]


class SqliteMemory:
    def __init__(self, path: str, *, pool_size: int = 4, retention_days: int = 30):
        self.path = path
        self.pool_size = max(1, int(pool_size))
        self.retention_days = max(1, int(retention_days))
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=self.pool_size)
        self._created = 0
        self._create_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._last_cleanup_monotonic = 0.0
        self._init_db()

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn
    
    def _acquire(self) -> sqlite3.Connection:
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            with self._create_lock:
                if self._created < self.pool_size:
                    self._created += 1
                    return self._new_connection()
            return self._pool.get()

    def _release(self, conn: sqlite3.Connection) -> None:
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            conn.close()

    def _with_conn(self, fn):
        conn = self._acquire()
        try:
            return fn(conn)
        finally:
            self._release(conn)

    def _init_db(self) -> None:
        def _run(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS short_term_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    session_id TEXT NOT NULL DEFAULT 'default',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS long_term_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    session_id TEXT NOT NULL DEFAULT 'default',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL
                )
                """
            )
            cols_short = {r[1] for r in conn.execute("PRAGMA table_info(short_term_messages)").fetchall()}
            if "session_id" not in cols_short:
                conn.execute("ALTER TABLE short_term_messages ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default'")
            cols_long = {r[1] for r in conn.execute("PRAGMA table_info(long_term_facts)").fetchall()}
            if "session_id" not in cols_long:
                conn.execute("ALTER TABLE long_term_facts ADD COLUMN session_id TEXT NOT NULL DEFAULT 'default'")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_short_term_ts ON short_term_messages(ts_ms)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_short_term_session_ts ON short_term_messages(session_id, ts_ms)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_long_term_key ON long_term_facts(key)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_long_term_session_ts ON long_term_facts(session_id, ts_ms)")
            conn.commit()

        self._with_conn(_run)
        self._cleanup_old_data_sync()

    def _cleanup_old_data_sync(self) -> None:
        cutoff_ms = int((time.time() - (self.retention_days * 86400)) * 1000)

        def _run(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM short_term_messages WHERE ts_ms < ?", (cutoff_ms,))
            conn.execute("DELETE FROM long_term_facts WHERE ts_ms < ?", (cutoff_ms,))
            conn.commit()

        self._with_conn(_run)

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup_monotonic < 600:
            return
        if not self._cleanup_lock.acquire(blocking=False):
            return
        try:
            if now - self._last_cleanup_monotonic < 600:
                return
            self._cleanup_old_data_sync()
            self._last_cleanup_monotonic = now
        finally:
            self._cleanup_lock.release()

    async def append_short_term(self, role: Role, content: str, ts_ms: int | None = None, session_id: str = "default") -> None:
        await asyncio.to_thread(self._append_short_term_sync, role, content, ts_ms, session_id)

    def _append_short_term_sync(self, role: Role, content: str, ts_ms: int | None, session_id: str) -> None:
        self._maybe_cleanup()

        def _run(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO short_term_messages(ts_ms, session_id, role, content) VALUES (?, ?, ?, ?)",
                (int(ts_ms or time.time() * 1000), session_id or "default", role, content),
            )
            conn.commit()

        self._with_conn(_run)

    async def get_recent_short_term(self, limit: int = 20, session_id: str = "default") -> list[dict]:
        return await asyncio.to_thread(self._get_recent_short_term_sync, limit, session_id)

    def _get_recent_short_term_sync(self, limit: int, session_id: str) -> list[dict]:
        def _run(conn: sqlite3.Connection) -> list[dict]:
            cur = conn.execute(
                "SELECT ts_ms, role, content FROM short_term_messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id or "default", limit),
            )
            rows = cur.fetchall()
            return [{"ts_ms": ts_ms, "role": role, "content": content} for (ts_ms, role, content) in rows[::-1]]

        return self._with_conn(_run)

    async def delete_short_term_before(self, ts_ms: int, session_id: str = "default") -> None:
        await asyncio.to_thread(self._delete_short_term_before_sync, ts_ms, session_id)

    def _delete_short_term_before_sync(self, ts_ms: int, session_id: str) -> None:
        def _run(conn: sqlite3.Connection) -> None:
            conn.execute(
                "DELETE FROM short_term_messages WHERE session_id = ? AND ts_ms <= ?",
                (session_id or "default", ts_ms),
            )
            conn.commit()

        self._with_conn(_run)

    async def upsert_long_term(self, key: str, value: str, ts_ms: int | None = None, session_id: str = "default") -> None:
        await asyncio.to_thread(self._upsert_long_term_sync, key, value, ts_ms, session_id)

    def _upsert_long_term_sync(self, key: str, value: str, ts_ms: int | None, session_id: str) -> None:
        self._maybe_cleanup()

        def _run(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO long_term_facts(ts_ms, session_id, key, value) VALUES (?, ?, ?, ?)",
                (int(ts_ms or time.time() * 1000), session_id or "default", key, value),
            )
            conn.commit()

        self._with_conn(_run)

    async def search_long_term(self, key_prefix: str, limit: int = 20, session_id: str = "default") -> list[dict]:
        return await asyncio.to_thread(self._search_long_term_sync, key_prefix, limit, session_id)

    def _search_long_term_sync(self, key_prefix: str, limit: int, session_id: str) -> list[dict]:
        def _run(conn: sqlite3.Connection) -> list[dict]:
            cur = conn.execute(
                "SELECT ts_ms, key, value FROM long_term_facts WHERE session_id = ? AND key LIKE ? ORDER BY id DESC LIMIT ?",
                (session_id or "default", f"{key_prefix}%", limit),
            )
            rows = cur.fetchall()
            return [{"ts_ms": ts_ms, "key": key, "value": value} for (ts_ms, key, value) in rows]

        return self._with_conn(_run)

    async def get_all_long_term_facts(self, session_id: str = "default") -> dict[str, str]:
        return await asyncio.to_thread(self._get_all_long_term_facts_sync, session_id)

    def _get_all_long_term_facts_sync(self, session_id: str) -> dict[str, str]:
        def _run(conn: sqlite3.Connection) -> dict[str, str]:
            cur = conn.execute(
                "SELECT key, value FROM long_term_facts WHERE session_id = ? ORDER BY id ASC",
                (session_id or "default",),
            )
            rows = cur.fetchall()
            # If multiple inserts happened for the same key, the latest (by ASC order) overwrites the earlier ones in the dict
            return {key: value for (key, value) in rows}

        return self._with_conn(_run)

