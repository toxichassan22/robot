from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


class VoskMicListener:
    def __init__(self, model_path: str | None):
        self.model_path = model_path

    def validate_model_path(self) -> str:
        if not self.model_path:
            raise ValueError("--vosk-model-path is required for mic mode")
        p = Path(self.model_path)
        if p.exists() and p.is_file() and p.suffix.lower() in {".zip", ".7z", ".rar"}:
            raise ValueError(
                f"Vosk model path points to an archive ({p.suffix}). Extract it first, then pass the extracted folder path: {p}"
            )
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Invalid Vosk model path: {p}. Provide the extracted model folder path.")

        if (p / "blobs").exists() and (p / "manifests").exists():
            raise ValueError(
                "This path looks like an Ollama models directory (blobs/manifests). "
                "Vosk needs a separate speech model folder that contains am/ and conf/. "
                f"Path: {p}"
            )
        missing: list[str] = []
        if not (p / "am").exists():
            missing.append("am/")
        if not (p / "conf").exists():
            missing.append("conf/")
        if missing:
            raise ValueError(
                "Vosk model folder looks incomplete. Missing: "
                + ", ".join(missing)
                + f". Path: {p}"
            )
        return str(p)

    async def stream_text(self):
        try:
            import sounddevice as sd  # type: ignore
        except Exception as e:
            raise RuntimeError("sounddevice is required for mic input") from e
        try:
            from vosk import KaldiRecognizer, Model  # type: ignore
        except Exception as e:
            raise RuntimeError("vosk is required for offline STT") from e

        model_path = self.validate_model_path()
        try:
            model = Model(model_path)
        except Exception as e:
            raise RuntimeError(
                "Failed to load Vosk model. Ensure --vosk-model-path points to the extracted model folder (not the zip). "
                f"Path: {model_path}"
            ) from e
        sample_rate = 16000
        rec = KaldiRecognizer(model, sample_rate)

        q: asyncio.Queue[bytes] = asyncio.Queue()

        def _cb(indata, frames, time_info, status):
            q.put_nowait(bytes(indata))

        with sd.RawInputStream(samplerate=sample_rate, blocksize=8000, dtype="int16", channels=1, callback=_cb):
            while True:
                data = await q.get()
                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = (res.get("text") or "").strip()
                    if text:
                        yield text
                else:
                    res = json.loads(rec.PartialResult())
                    _ = res.get("partial")


def find_vosk_models(roots: list[str], max_depth: int = 6) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    for root in roots:
        try:
            rp = Path(root).expanduser().resolve()
        except Exception:
            continue
        if not rp.exists() or not rp.is_dir():
            continue

        stack: list[tuple[Path, int]] = [(rp, 0)]
        while stack:
            cur, depth = stack.pop()
            try:
                am = cur / "am"
                conf = cur / "conf"
                if am.exists() and conf.exists():
                    s = str(cur)
                    if s not in seen:
                        seen.add(s)
                        candidates.append(s)
                    continue

                if depth >= max_depth:
                    continue

                for child in cur.iterdir():
                    if child.is_dir():
                        name = child.name.lower()
                        if name in {"node_modules", ".git", ".venv", "venv", "__pycache__"}:
                            continue
                        stack.append((child, depth + 1))
            except Exception:
                continue

    candidates.sort()
    return candidates
