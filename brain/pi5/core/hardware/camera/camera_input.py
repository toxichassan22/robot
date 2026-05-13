from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator

from brain.types import VideoFrame


@dataclass
class CameraConfig:
    source: int | str = 0
    width: int | None = None
    height: int | None = None
    fps: float | None = None


class CameraInput:
    def __init__(self, cfg: CameraConfig | None = None):
        self.cfg = cfg or CameraConfig()
        self._cap = None

    def open(self) -> None:
        if self._cap is not None:
            return
        try:
            import cv2  # type: ignore
        except Exception as e:
            raise RuntimeError("opencv-python is required for camera input") from e
        self._cv2 = cv2
        self._cap = cv2.VideoCapture(self.cfg.source)
        if self.cfg.width:
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.cfg.width))
        if self.cfg.height:
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.cfg.height))
        if self.cfg.fps:
            self._cap.set(cv2.CAP_PROP_FPS, float(self.cfg.fps))

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            finally:
                self._cap = None

    def stream_frames(self) -> Iterator[VideoFrame]:
        self.open()
        cap = self._cap
        cv2 = self._cv2
        assert cap is not None
        last = 0.0
        period = 0.0
        if self.cfg.fps and self.cfg.fps > 0:
            period = 1.0 / float(self.cfg.fps)
        while True:
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.02)
                continue
            if period:
                now = time.monotonic()
                if last and now - last < period:
                    continue
                last = now
            h, w = frame.shape[:2]
            yield VideoFrame(data=frame, width=int(w), height=int(h), format="bgr")

