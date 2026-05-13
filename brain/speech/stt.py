import abc
import json
import logging
import os
import queue
import struct
import threading
import tempfile
import time
import wave

try:
    from vosk import Model, KaldiRecognizer
    import vosk
    # Reduce vosk logging
    vosk.SetLogLevel(-1)
    VOSK_AVAILABLE = True
except (ImportError, OSError, Exception) as e:
    VOSK_AVAILABLE = False
    logging.warning(f"vosk could not be initialized (Offline STT disabled): {e}")

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False
    logging.warning("SpeechRecognition not found. Google online STT disabled.")


class STTBase(abc.ABC):
    @abc.abstractmethod
    def accept_wave(self, data: bytes) -> bool:
        pass

    @abc.abstractmethod
    def result(self) -> str:
        pass
    
    @abc.abstractmethod
    def partial_result(self) -> str:
        pass


class VoskSTT(STTBase):
    def __init__(self, model_path: str, sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.rec = None
        self._load_model()

    def _load_model(self):
        if not VOSK_AVAILABLE:
            return

        if not os.path.exists(self.model_path):
            logging.error(f"Vosk model path not found: {self.model_path}")
            return

        try:
            logging.info(f"Loading Vosk model from {self.model_path}...")
            model = Model(self.model_path)
            self.rec = KaldiRecognizer(model, self.sample_rate)
            logging.info("Vosk model loaded.")
        except Exception as e:
            logging.error(f"Failed to load Vosk model: {e}")
            self.rec = None

    def accept_wave(self, data: bytes) -> bool:
        if not self.rec:
            return False
        return self.rec.AcceptWaveform(data)

    def result(self) -> str:
        if not self.rec:
            return ""
        res = json.loads(self.rec.Result())
        return res.get("text", "")

    def partial_result(self) -> str:
        if not self.rec:
            return ""
        res = json.loads(self.rec.PartialResult())
        return res.get("partial", "")


# ---------------------------------------------------------------------------
# Google Speech Recognition (Online STT)
# ---------------------------------------------------------------------------

class GoogleSTT(STTBase):
    """
    Online STT using Google Speech Recognition via the `speech_recognition` library.
    Accumulates raw PCM audio chunks and transcribes when a silence gap is detected
    or the buffer exceeds a size threshold.
    """

    # Voice-activity detection thresholds
    _SILENCE_THRESHOLD = 500       # RMS below this is considered silence
    _SILENCE_CHUNKS_NEEDED = 6     # ~0.6s of silence at 16kHz / 4000-sample blocks
    _MIN_SPEECH_BYTES = 8000       # Ignore very short bursts (< 0.25s)
    _MAX_BUFFER_BYTES = 960_000    # Force transcription after ~30s

    def __init__(self, language: str = "ar-EG", sample_rate: int = 16000):
        self.language = language
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._silence_count = 0
        self._last_result = ""
        self._partial = ""
        self._recognizer = sr.Recognizer() if SR_AVAILABLE else None

    # ---- helpers ----

    @staticmethod
    def _rms(data: bytes) -> float:
        """Compute root-mean-square of int16 PCM data."""
        count = len(data) // 2
        if count == 0:
            return 0.0
        shorts = struct.unpack(f"{count}h", data)
        sum_sq = sum(s * s for s in shorts)
        return (sum_sq / count) ** 0.5

    def _transcribe_buffer(self) -> str:
        """Send the accumulated buffer to Google and return the text."""
        if not self._recognizer or len(self._buffer) < self._MIN_SPEECH_BYTES:
            self._buffer.clear()
            return ""

        # Write buffer to a temporary WAV file
        tmp = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # int16
                wf.setframerate(self.sample_rate)
                wf.writeframes(bytes(self._buffer))

            with sr.AudioFile(tmp.name) as source:
                audio = self._recognizer.record(source)

            text = self._recognizer.recognize_google(audio, language=self.language)
            logging.info(f"GoogleSTT transcribed: {text}")
            return text.strip()
        except sr.UnknownValueError:
            logging.debug("GoogleSTT: could not understand audio")
            return ""
        except sr.RequestError as e:
            logging.error(f"GoogleSTT request error: {e}")
            return ""
        except Exception as e:
            logging.error(f"GoogleSTT error: {e}")
            return ""
        finally:
            self._buffer.clear()
            if tmp:
                try:
                    os.remove(tmp.name)
                except OSError:
                    pass

    # ---- STTBase interface ----

    def accept_wave(self, data: bytes) -> bool:
        if not SR_AVAILABLE:
            return False

        self._buffer.extend(data)
        rms = self._rms(data)

        if rms < self._SILENCE_THRESHOLD:
            self._silence_count += 1
        else:
            self._silence_count = 0

        # Trigger transcription on silence gap or buffer overflow
        has_speech = len(self._buffer) >= self._MIN_SPEECH_BYTES
        silence_detected = self._silence_count >= self._SILENCE_CHUNKS_NEEDED
        buffer_full = len(self._buffer) >= self._MAX_BUFFER_BYTES

        if has_speech and (silence_detected or buffer_full):
            self._last_result = self._transcribe_buffer()
            self._silence_count = 0
            return bool(self._last_result)

        return False

    def result(self) -> str:
        r = self._last_result
        self._last_result = ""
        return r

    def partial_result(self) -> str:
        # Google doesn't support partial results in this mode
        return ""


# ---------------------------------------------------------------------------
# Hybrid STT — switches between online and offline at runtime
# ---------------------------------------------------------------------------

class HybridSTT(STTBase):
    """
    Wraps an online and offline STT provider.
    Routes audio to the currently active provider based on `mode`.
    """

    def __init__(self, online: STTBase | None, offline: STTBase | None, mode: str = "offline"):
        self._online = online
        self._offline = offline
        self._mode = mode.lower().strip()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        new_mode = mode.lower().strip()
        if new_mode not in ("online", "offline"):
            logging.warning(f"HybridSTT: unknown mode '{mode}', keeping '{self._mode}'")
            return
        if new_mode != self._mode:
            logging.info(f"HybridSTT: switching from '{self._mode}' to '{new_mode}'")
            self._mode = new_mode

    @property
    def _active(self) -> STTBase | None:
        if self._mode == "online":
            return self._online
        return self._offline

    def accept_wave(self, data: bytes) -> bool:
        p = self._active
        if p is None:
            return False
        return p.accept_wave(data)

    def result(self) -> str:
        p = self._active
        return p.result() if p else ""

    def partial_result(self) -> str:
        p = self._active
        return p.partial_result() if p else ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_stt(
    provider: str = "vosk",
    online_enabled: bool = False,
    language: str = "ar-EG",
    vosk_model_path: str = "",
    sample_rate: int = 16000,
) -> STTBase:
    """
    Factory function to create the appropriate STT provider.
    
    Args:
        provider: "vosk" | "google" — the primary provider preference.
        online_enabled: If True, use the online provider (Google).
        language: BCP-47 language tag (e.g., "ar-EG").
        vosk_model_path: Path to the Vosk model directory.
        sample_rate: Audio sample rate in Hz.
    """
    # Build offline provider
    offline: STTBase | None = None
    if VOSK_AVAILABLE and vosk_model_path:
        offline = VoskSTT(model_path=vosk_model_path, sample_rate=sample_rate)
        if offline.rec is None:
            logging.warning("VoskSTT failed to load model. Offline STT unavailable.")
            offline = None

    # Build online provider
    online: STTBase | None = None
    if SR_AVAILABLE:
        online = GoogleSTT(language=language, sample_rate=sample_rate)

    # Determine initial mode
    if provider == "google" or online_enabled:
        mode = "online"
    else:
        mode = "offline"

    # If only one provider is available, use it directly
    if online is None and offline is None:
        logging.error("No STT providers available! Speech recognition will be disabled.")
        return VoskSTT(model_path="", sample_rate=sample_rate)  # returns a no-op

    if online is None:
        if mode == "online":
            logging.warning("Google STT unavailable. Falling back to Vosk (offline).")
        return offline  # type: ignore

    if offline is None:
        if mode == "offline":
            logging.warning("Vosk STT unavailable. Falling back to Google (online).")
        return online

    logging.info(f"HybridSTT initialized — mode={mode}, online=GoogleSTT, offline=VoskSTT")
    return HybridSTT(online=online, offline=offline, mode=mode)
