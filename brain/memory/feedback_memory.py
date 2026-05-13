from __future__ import annotations

import asyncio
import json
import queue
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeedbackRow:
    id: int
    ts_ms: int
    interaction_id: str
    rating: int
    correction: str
    context: dict[str, Any]


class FeedbackMemory:
    def __init__(self, path: str, *, pool_size: int = 2):
        self.path = path
        self.pool_size = max(1, int(pool_size))
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=self.pool_size)
        self._created = 0
        self._create_lock = threading.Lock()
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
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_ms INTEGER NOT NULL,
                    interaction_id TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    correction TEXT NOT NULL,
                    context TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts_ms)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_interaction ON feedback(interaction_id)")
            conn.commit()

        self._with_conn(_run)

    async def store_feedback(
        self, interaction_id: str, rating: int, correction: str, context: dict[str, Any] | None = None, ts_ms: int | None = None
    ) -> None:
        await asyncio.to_thread(self._store_feedback_sync, interaction_id, rating, correction, context, ts_ms)

    def _store_feedback_sync(
        self, interaction_id: str, rating: int, correction: str, context: dict[str, Any] | None, ts_ms: int | None
    ) -> None:
        iid = str(interaction_id or "").strip() or "unknown"
        r = 1 if int(rating) > 0 else 0
        corr = str(correction or "")
        ctx = context if isinstance(context, dict) else {}
        raw_ctx = json.dumps(ctx, ensure_ascii=False)

        def _run(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO feedback(ts_ms, interaction_id, rating, correction, context) VALUES (?, ?, ?, ?, ?)",
                (int(ts_ms or time.time() * 1000), iid, r, corr, raw_ctx),
            )
            conn.commit()

        self._with_conn(_run)

    async def get_recent(self, limit: int = 10) -> list[FeedbackRow]:
        return await asyncio.to_thread(self._get_recent_sync, limit)

    def _get_recent_sync(self, limit: int) -> list[FeedbackRow]:
        lim = max(1, min(int(limit), 50))

        def _run(conn: sqlite3.Connection) -> list[FeedbackRow]:
            cur = conn.execute(
                "SELECT id, ts_ms, interaction_id, rating, correction, context FROM feedback ORDER BY id DESC LIMIT ?",
                (lim,),
            )
            rows = cur.fetchall()
            out: list[FeedbackRow] = []
            for (fid, ts_ms, interaction_id, rating, correction, ctx) in rows[::-1]:
                try:
                    parsed = json.loads(ctx) if isinstance(ctx, str) and ctx.strip() else {}
                except Exception:
                    parsed = {}
                out.append(
                    FeedbackRow(
                        id=int(fid),
                        ts_ms=int(ts_ms),
                        interaction_id=str(interaction_id),
                        rating=int(rating),
                        correction=str(correction),
                        context=parsed if isinstance(parsed, dict) else {},
                    )
                )
            return out

        return self._with_conn(_run)

    async def get_feedback_stats(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_feedback_stats_sync)

    def _get_feedback_stats_sync(self) -> dict[str, Any]:
        def _run(conn: sqlite3.Connection) -> dict[str, Any]:
            cur = conn.execute("SELECT COUNT(*), SUM(rating) FROM feedback")
            total, sum_rating = cur.fetchone() or (0, 0)
            total_i = int(total or 0)
            pos = int(sum_rating or 0)
            neg = total_i - pos
            return {"total": total_i, "positive": pos, "negative": neg}

        return self._with_conn(_run)

