from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


def now_ms() -> int:
    return int(time.time() * 1000)


def copy_frame(frame: Any) -> Any:
    copier = getattr(frame, "copy", None)
    if callable(copier):
        try:
            return copier()
        except Exception:
            return frame
    return frame


@dataclass(frozen=True)
class TimestampedFrame:
    ts_ms: int
    frame_index: int
    frame: Any

    def copied(self) -> "TimestampedFrame":
        return TimestampedFrame(
            ts_ms=self.ts_ms,
            frame_index=self.frame_index,
            frame=copy_frame(self.frame),
        )


def _sample_evenly(frames: list[TimestampedFrame], max_frames: int) -> list[TimestampedFrame]:
    if max_frames <= 0 or len(frames) <= max_frames:
        return frames
    if max_frames == 1:
        return [frames[len(frames) // 2]]
    last = len(frames) - 1
    indexes = [round(i * last / (max_frames - 1)) for i in range(max_frames)]
    return [frames[i] for i in indexes]


class FrameRingBuffer:
    def __init__(self, max_frames: int = 180):
        self._frames: deque[TimestampedFrame] = deque(maxlen=max(1, int(max_frames)))

    def append(self, frame: Any, *, ts_ms: int | None = None, frame_index: int = 0) -> TimestampedFrame:
        record = TimestampedFrame(
            ts_ms=now_ms() if ts_ms is None else int(ts_ms),
            frame_index=int(frame_index),
            frame=frame,
        )
        self._frames.append(record)
        return record

    def latest(self) -> TimestampedFrame | None:
        if not self._frames:
            return None
        return self._frames[-1].copied()

    def snapshot(self) -> list[TimestampedFrame]:
        return [record.copied() for record in self._frames]

    def nearest(self, target_ts_ms: int, *, max_delta_ms: int | None = None) -> TimestampedFrame | None:
        if not self._frames:
            return None
        target = int(target_ts_ms)
        best = min(self._frames, key=lambda record: abs(record.ts_ms - target))
        if max_delta_ms is not None and abs(best.ts_ms - target) > int(max_delta_ms):
            return None
        return best.copied()

    def window_around(
        self,
        center_ts_ms: int,
        *,
        before_ms: int = 700,
        after_ms: int = 0,
        max_frames: int = 3,
    ) -> list[TimestampedFrame]:
        center = int(center_ts_ms)
        start = center - max(0, int(before_ms))
        end = center + max(0, int(after_ms))
        frames = [record for record in self._frames if start <= record.ts_ms <= end]
        if not frames:
            nearest = self.nearest(center, max_delta_ms=max(before_ms, after_ms, 1))
            return [nearest] if nearest is not None else []
        return [record.copied() for record in _sample_evenly(frames, max_frames)]


@dataclass(frozen=True)
class VLMFrameCandidate:
    priority: int
    frame_ts_ms: int
    image_bytes: bytes
    prompt: str
    event_type: str
    created_ms: int = field(default_factory=now_ms)

    def is_stale(self, now_ts_ms: int, max_age_ms: int) -> bool:
        return int(now_ts_ms) - int(self.frame_ts_ms) > int(max_age_ms)


class PriorityFrameQueue:
    def __init__(self, maxsize: int = 8, max_age_ms: int = 10_000):
        self.maxsize = max(1, int(maxsize))
        self.max_age_ms = max(1, int(max_age_ms))
        self._items: list[VLMFrameCandidate] = []
        self._lock = threading.Lock()
        self._dropped = 0
        self._dropped_stale = 0

    def _discard_stale_locked(self, now_ts_ms: int) -> None:
        kept: list[VLMFrameCandidate] = []
        for item in self._items:
            if item.is_stale(now_ts_ms, self.max_age_ms):
                self._dropped_stale += 1
            else:
                kept.append(item)
        self._items = kept

    @staticmethod
    def _replacement_rank(item: VLMFrameCandidate) -> tuple[int, int, int]:
        return (int(item.priority), int(item.frame_ts_ms), int(item.created_ms))

    @staticmethod
    def _pop_rank(item: VLMFrameCandidate) -> tuple[int, int]:
        return (int(item.priority), -int(item.created_ms))

    def push(self, candidate: VLMFrameCandidate) -> bool:
        with self._lock:
            self._discard_stale_locked(now_ms())
            if len(self._items) < self.maxsize:
                self._items.append(candidate)
                return True

            worst_index = min(
                range(len(self._items)),
                key=lambda i: self._replacement_rank(self._items[i]),
            )
            worst = self._items[worst_index]
            if self._replacement_rank(candidate) <= self._replacement_rank(worst):
                self._dropped += 1
                return False

            self._items.pop(worst_index)
            self._items.append(candidate)
            self._dropped += 1
            return True

    def pop(self) -> VLMFrameCandidate | None:
        with self._lock:
            self._discard_stale_locked(now_ms())
            if not self._items:
                return None
            best_index = max(range(len(self._items)), key=lambda i: self._pop_rank(self._items[i]))
            return self._items.pop(best_index)

    def qsize(self) -> int:
        with self._lock:
            self._discard_stale_locked(now_ms())
            return len(self._items)

    def snapshot(self) -> list[VLMFrameCandidate]:
        with self._lock:
            self._discard_stale_locked(now_ms())
            return sorted(self._items, key=self._pop_rank, reverse=True)

    def stats(self) -> dict[str, int]:
        with self._lock:
            self._discard_stale_locked(now_ms())
            return {
                "size": len(self._items),
                "max_size": self.maxsize,
                "dropped": self._dropped,
                "dropped_stale": self._dropped_stale,
                "max_age_ms": self.max_age_ms,
            }
