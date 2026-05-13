from __future__ import annotations

from dataclasses import dataclass

from brain.types import VideoFrame


@dataclass(frozen=True)
class VisionPreprocessResult:
    frame: VideoFrame | None
    meta: dict


class VisionPreprocessor:
    def __init__(self):
        self._cv2 = None
        self._face = None

    def process(self, frame: VideoFrame) -> VisionPreprocessResult:
        faces = []
        try:
            import cv2  # type: ignore

            self._cv2 = cv2
            if self._face is None:
                self._face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            img = frame.data
            if img is not None:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                det = self._face.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
                faces = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in det]
        except Exception:
            faces = []

        meta = {"selected": True, "faces": faces, "objects": []}
        return VisionPreprocessResult(frame=frame, meta=meta)
