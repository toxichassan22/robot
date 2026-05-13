from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from brain.types import GestureData


@dataclass
class GestureDetectorConfig:
    max_num_hands: int = 1
    min_detection_confidence: float = 0.6
    min_tracking_confidence: float = 0.6


class MediaPipeHandGestureDetector:
    def __init__(self, cfg: GestureDetectorConfig | None = None):
        self.cfg = cfg or GestureDetectorConfig()
        self._hands = None
        self._last_wave: dict[str, tuple[float, float]] = {}
        self._last_wave_ts = 0.0

    def _ensure(self) -> Any:
        if self._hands is not None:
            return self._hands
        try:
            import mediapipe as mp  # type: ignore
        except Exception as e:
            raise RuntimeError("mediapipe is required for gesture detection") from e
        self._mp = mp
        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=int(self.cfg.max_num_hands),
            model_complexity=0,
            min_detection_confidence=float(self.cfg.min_detection_confidence),
            min_tracking_confidence=float(self.cfg.min_tracking_confidence),
        )
        return self._hands

    def detect(self, frame_bgr: Any) -> list[GestureData]:
        hands = self._ensure()
        try:
            import cv2  # type: ignore
        except Exception as e:
            raise RuntimeError("opencv-python is required for gesture detection") from e

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        res = hands.process(rgb)
        if not res.multi_hand_landmarks:
            return []

        out: list[GestureData] = []
        for i, lm in enumerate(res.multi_hand_landmarks):
            score = 0.0
            handed = "unknown"
            if res.multi_handedness and i < len(res.multi_handedness):
                c = res.multi_handedness[i].classification[0]
                score = float(getattr(c, "score", 0.0) or 0.0)
                handed = str(getattr(c, "label", "unknown") or "unknown").lower()

            gesture_type, conf = self._classify(lm, handed=handed, base_conf=score)
            out.append(GestureData(gesture_type=gesture_type, confidence=conf, hand_landmarks=lm))
        return out

    def _classify(self, lm: Any, *, handed: str, base_conf: float) -> tuple[str, float]:
        pts = lm.landmark
        wrist = pts[0]
        thumb_tip = pts[4]
        index_tip = pts[8]
        middle_tip = pts[12]
        ring_tip = pts[16]
        pinky_tip = pts[20]

        index_pip = pts[6]
        middle_pip = pts[10]
        ring_pip = pts[14]
        pinky_pip = pts[18]

        index_up = index_tip.y < index_pip.y
        middle_up = middle_tip.y < middle_pip.y
        ring_up = ring_tip.y < ring_pip.y
        pinky_up = pinky_tip.y < pinky_pip.y

        if handed in {"left", "right"}:
            if handed == "right":
                thumb_up = thumb_tip.x < pts[3].x
            else:
                thumb_up = thumb_tip.x > pts[3].x
        else:
            thumb_up = abs(thumb_tip.x - wrist.x) > 0.08

        extended = {
            "thumb": thumb_up,
            "index": index_up,
            "middle": middle_up,
            "ring": ring_up,
            "pinky": pinky_up,
        }
        ext_count = sum(1 for v in extended.values() if v)

        if extended["thumb"] and not (extended["index"] or extended["middle"] or extended["ring"] or extended["pinky"]):
            if thumb_tip.y < wrist.y - 0.02:
                return ("thumbs_up", max(base_conf, 0.85))
            if thumb_tip.y > wrist.y + 0.02:
                return ("thumbs_down", max(base_conf, 0.85))
            return ("thumbs", max(base_conf, 0.75))

        if extended["index"] and not (extended["middle"] or extended["ring"] or extended["pinky"]):
            return ("pointing", max(base_conf, 0.8))

        if ext_count >= 4:
            if self._is_wave(lm):
                return ("waving", max(base_conf, 0.8))
            return ("paper", max(base_conf, 0.75))

        if ext_count <= 1:
            return ("rock", max(base_conf, 0.75))

        if extended["index"] and extended["middle"] and not (extended["ring"] or extended["pinky"]):
            return ("scissors", max(base_conf, 0.8))

        return ("unknown", max(base_conf, 0.5))

    def _is_wave(self, lm: Any) -> bool:
        now = time.monotonic()
        pts = lm.landmark
        wrist = pts[0]
        key = "wrist"

        prev = self._last_wave.get(key)
        self._last_wave[key] = (float(wrist.x), float(wrist.y))
        if prev is None:
            return False

        dx = abs(float(wrist.x) - float(prev[0]))
        dy = abs(float(wrist.y) - float(prev[1]))
        moved = math.hypot(dx, dy)
        if moved < 0.06:
            return False

        if now - self._last_wave_ts < 0.6:
            return True
        self._last_wave_ts = now
        return True

