from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class AudioChunk:
    pcm16: bytes
    sample_rate_hz: int


@dataclass(frozen=True)
class VideoFrame:
    data: Any
    width: int
    height: int
    format: str


@dataclass(frozen=True)
class SensorPacket:
    ts_ms: int
    values: dict[str, Any]


@dataclass(frozen=True)
class GestureData:
    gesture_type: str
    confidence: float
    hand_landmarks: Any


@dataclass(frozen=True)
class MotionCommand:
    direction: str
    speed: float
    duration_ms: int


@dataclass(frozen=True)
class ServoCommand:
    servo_id: int
    angle: float


@dataclass(frozen=True)
class PerceptionState:
    ts_ms: int
    text: str | None
    vision: dict[str, Any] | None = None
    sensors: dict[str, Any] | None = None
    gestures: dict[str, Any] | None = None
    vision_desc: str | None = None
    summary: str | None = None
    motion_detected: bool = False


@dataclass(frozen=True)
class ActionCommand:
    kind: str
    payload: dict[str, Any]
