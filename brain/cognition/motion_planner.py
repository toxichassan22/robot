from __future__ import annotations

from dataclasses import dataclass

from brain.types import MotionCommand


@dataclass
class MotionPlanConfig:
    min_safe_distance_cm: float = 20.0
    slow_distance_cm: float = 40.0
    max_speed: float = 1.0
    min_speed: float = 0.0
    max_duration_ms: int = 10_000


class MotionPlanner:
    def __init__(self, cfg: MotionPlanConfig | None = None):
        self.cfg = cfg or MotionPlanConfig()

    def plan(self, direction: str, speed: float, duration_ms: int, sensors: dict | None) -> MotionCommand:
        d = str(direction or "").strip().lower() or "stop"
        s = float(speed)
        ms = int(duration_ms)
        if ms < 0:
            ms = 0
        if ms > int(self.cfg.max_duration_ms):
            ms = int(self.cfg.max_duration_ms)
        if s < float(self.cfg.min_speed):
            s = float(self.cfg.min_speed)
        if s > float(self.cfg.max_speed):
            s = float(self.cfg.max_speed)

        dist = None
        if sensors and isinstance(sensors, dict):
            v = sensors.get("obstacle_distance_cm")
            if isinstance(v, (int, float)):
                dist = float(v)

        if d in {"forward", "fwd"} and dist is not None:
            if dist < float(self.cfg.min_safe_distance_cm):
                return MotionCommand(direction="stop", speed=0.0, duration_ms=0)
            if dist < float(self.cfg.slow_distance_cm):
                ratio = (dist - float(self.cfg.min_safe_distance_cm)) / max(
                    1.0, float(self.cfg.slow_distance_cm) - float(self.cfg.min_safe_distance_cm)
                )
                s = max(0.15, min(s, ratio))

        if d not in {"forward", "backward", "left", "right", "stop"}:
            d = "stop"
            s = 0.0
            ms = 0

        if d == "stop":
            s = 0.0
            ms = 0
        return MotionCommand(direction=d, speed=s, duration_ms=ms)

