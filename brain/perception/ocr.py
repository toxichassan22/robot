from __future__ import annotations

import logging
from typing import Any


class OCRReader:
    def __init__(self, *, min_confidence: float = 45.0):
        self.min_confidence = float(min_confidence)
        self._backend: str | None = None
        self._easyocr_reader: Any | None = None
        self._available: bool | None = None

    @property
    def backend(self) -> str | None:
        self._ensure_backend()
        return self._backend

    def _ensure_backend(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import pytesseract  # noqa: F401
            self._backend = "pytesseract"
            self._available = True
            return True
        except Exception:
            pass

        try:
            import easyocr  # type: ignore
            self._easyocr_reader = easyocr.Reader(["ar", "en"], gpu=False, verbose=False)
            self._backend = "easyocr"
            self._available = True
            return True
        except Exception:
            pass

        self._available = False
        self._backend = None
        return False

    @staticmethod
    def _preprocess(frame: Any) -> Any:
        try:
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.bilateralFilter(gray, 5, 75, 75)
            return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        except Exception:
            return frame

    def read(self, frame: Any) -> dict[str, Any] | None:
        if frame is None or not self._ensure_backend():
            return None
        if self._backend == "pytesseract":
            return self._read_tesseract(frame)
        if self._backend == "easyocr":
            return self._read_easyocr(frame)
        return None

    def _read_tesseract(self, frame: Any) -> dict[str, Any] | None:
        try:
            import pytesseract

            image = self._preprocess(frame)
            data = pytesseract.image_to_data(
                image,
                lang="ara+eng",
                config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
            words: list[str] = []
            confidences: list[float] = []
            count = len(data.get("text", []))
            for i in range(count):
                text = str(data["text"][i] or "").strip()
                if not text:
                    continue
                try:
                    conf = float(data["conf"][i])
                except Exception:
                    conf = -1.0
                if conf >= self.min_confidence:
                    words.append(text)
                    confidences.append(conf)
            if not words:
                return None
            return {
                "text": " ".join(words),
                "backend": "pytesseract",
                "confidence": round(sum(confidences) / max(1, len(confidences)), 1),
                "word_count": len(words),
            }
        except Exception as e:
            logging.debug(f"pytesseract OCR unavailable or failed: {e}")
            return None

    def _read_easyocr(self, frame: Any) -> dict[str, Any] | None:
        try:
            if self._easyocr_reader is None:
                return None
            results = self._easyocr_reader.readtext(frame, detail=1, paragraph=False)
            words: list[str] = []
            confidences: list[float] = []
            for item in results or []:
                if len(item) < 3:
                    continue
                text = str(item[1] or "").strip()
                conf = float(item[2] or 0.0) * 100.0
                if text and conf >= self.min_confidence:
                    words.append(text)
                    confidences.append(conf)
            if not words:
                return None
            return {
                "text": " ".join(words),
                "backend": "easyocr",
                "confidence": round(sum(confidences) / max(1, len(confidences)), 1),
                "word_count": len(words),
            }
        except Exception as e:
            logging.debug(f"easyocr OCR failed: {e}")
            return None
