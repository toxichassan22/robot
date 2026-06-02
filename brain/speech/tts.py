import os
import abc
import asyncio
import logging
import queue
import tempfile
import threading
import time
import pyaudio
from google import genai
from google.genai import types

try:
    import pyttsx3  # type: ignore
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False
    logging.warning("pyttsx3 not found. pyttsx3 TTS disabled.")

try:
    import edge_tts  # noqa: F401 # type: ignore
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logging.warning("edge_tts not found. Edge TTS disabled.")

try:
    from piper import PiperVoice  # type: ignore
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    logging.warning("piper-tts not found. Piper TTS disabled.")

try:
    from gtts import gTTS as _gTTS  # type: ignore
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False
    logging.warning("gTTS not found. Google TTS disabled.")

try:
    from google.cloud import texttospeech as _gcloud_tts  # type: ignore
    GCLOUD_TTS_AVAILABLE = True
except ImportError:
    GCLOUD_TTS_AVAILABLE = False
    logging.warning("google-cloud-texttospeech not found. Premium Google TTS disabled.")

from brain.speech.chatterbox_client import synthesize_with_chatterbox
from brain.speech.gemini_live_audio import (
    build_live_audio_config,
    require_single_gemini_api_key,
    resolve_live_model,
    send_text_turn,
)
from brain.speech.voice_utils import edge_prosody, normalize_tts_text, pick_edge_voice

class TTSBase(abc.ABC):
    @abc.abstractmethod
    def say(self, text: str):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class EdgeTTS(TTSBase):
    def __init__(self, voice_gender="female", language="ar-EG", voice_uri="", tts_rate=1.0):
        self.queue: queue.Queue = queue.Queue()
        self.thread = None
        self.running = False
        self.voice_gender = voice_gender
        self.language = language
        self.voice_uri = voice_uri
        self.tts_rate = tts_rate

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def say(self, text: str):
        self.queue.put(text)

    def _run_loop(self):
        while self.running:
            try:
                text = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            prepared = normalize_tts_text(text, language=self.language)
            if not prepared:
                continue

            try:
                self._play_text(prepared)
            except Exception as exc:
                logging.error(f"Edge TTS playback failed: {exc}")

    def _play_text(self, text: str):
        import edge_tts  # type: ignore

        gender = self.voice_gender.lower()
        if gender == "both":
            import random
            gender = random.choice(["male", "female"])
        voice = pick_edge_voice(language=self.language, voice_gender=gender, explicit_voice=self.voice_uri)
        rate, pitch = edge_prosody(language=self.language, tts_rate=self.tts_rate)
        logging.info(f"Edge TTS: using voice '{voice}' ({gender}), rate={rate}, pitch={pitch}")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            async def synthesize() -> None:
                communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
                await communicate.save(temp_path)

            # Use a fresh event loop to avoid conflicts with the main asyncio loop
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(synthesize())
            finally:
                loop.close()
            
            logging.info(f"Edge TTS: Audio saved to {temp_path}, playing...")
            self._play_audio_file(temp_path)
        except Exception as exc:
            logging.error(f"Edge TTS synthesis/playback error: {exc}")
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def _play_audio_file(self, path: str) -> None:
        if os.name == "nt":
            self._play_audio_file_windows(path)
            return

        # Linux / Raspberry Pi fallback: convert MP3 → WAV via ffmpeg, play with sounddevice
        self._play_audio_file_linux(path)

    @staticmethod
    def _play_audio_file_windows(path: str) -> None:
        try:
            from edge_playback.win32_playback import play_mp3_win32
            play_mp3_win32(path)
        except ImportError:
            # Fallback: use winsound if edge_playback is not installed
            import subprocess
            wav_path = path.replace(".mp3", "_edge.wav")
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", path, wav_path],
                    capture_output=True, timeout=10,
                )
                import winsound
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            except Exception as e:
                logging.error(f"Edge TTS Windows fallback playback failed: {e}")
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    @staticmethod
    def _play_audio_file_linux(path: str) -> None:
        """Convert MP3 to WAV via ffmpeg and play with sounddevice."""
        import subprocess
        wav_path = path.replace(".mp3", "_edge.wav")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", path, "-ar", "24000", "-ac", "1", wav_path],
                capture_output=True, timeout=10,
            )
            import soundfile as sf  # type: ignore
            import sounddevice as sd  # type: ignore
            data, sr = sf.read(wav_path, dtype="float32")
            sd.play(data, sr)
            sd.wait()
        except FileNotFoundError:
            logging.error("Edge TTS: ffmpeg not found. Install ffmpeg for Linux audio playback.")
        except Exception as e:
            logging.error(f"Edge TTS Linux playback failed: {e}")
        finally:
            try:
                os.remove(wav_path)
            except OSError:
                pass


class GoogleTTS(TTSBase):
    """High-quality Arabic TTS using Google Cloud Neural2 Voices."""

    def __init__(self, language="ar-EG", voice_gender="female", tts_rate=1.05):
        self.queue: queue.Queue = queue.Queue()
        self.thread = None
        self.running = False
        self.language = language
        self.voice_gender = voice_gender
        self.tts_rate = tts_rate
        self.client = None

    def start(self):
        if self.running:
            return
        self.running = True
        try:
            if GCLOUD_TTS_AVAILABLE:
                self.client = _gcloud_tts.TextToSpeechClient()
        except Exception as e:
            logging.error(f"Google Cloud TTS initialization failed (check GOOGLE_APPLICATION_CREDENTIALS): {e}")
            self.client = None
            
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logging.info(f"Google Cloud TTS started (lang={self.language}, gender={self.voice_gender})")

    def stop(self):
        self.running = False

    def say(self, text: str):
        self.queue.put(text)

    def _run_loop(self):
        while self.running:
            try:
                text = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            prepared = normalize_tts_text(text, language=self.language)
            if not prepared:
                continue

            try:
                if self.client:
                    self._play_text_cloud(prepared)
                else:
                    self._play_text_gtts_fallback(prepared)
            except Exception as exc:
                logging.error(f"Google TTS playback failed: {exc}")

    def _play_text_cloud(self, text: str):
        # ar-EG-Neural2-A: Female
        # ar-EG-Neural2-B: Male
        gender = self.voice_gender.lower()
        if gender == "both":
            import random
            gender = random.choice(["male", "female"])
        voice_name = "ar-EG-Neural2-A" if gender == 'female' else "ar-EG-Neural2-B"
        
        synthesis_input = _gcloud_tts.SynthesisInput(text=text)
        voice = _gcloud_tts.VoiceSelectionParams(
            language_code="ar-EG",
            name=voice_name
        )
        audio_config = _gcloud_tts.AudioConfig(
            audio_encoding=_gcloud_tts.AudioEncoding.MP3,
            speaking_rate=self.tts_rate, 
            pitch=0.0
        )
        
        try:
            response = self.client.synthesize_speech(
                input=synthesis_input, 
                voice=voice, 
                audio_config=audio_config
            )
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(response.audio_content)
                
            logging.info(f"Google Cloud TTS: Saved audio for '{text[:40]}...'")
            self._play_audio_file(temp_path)
            try:
                os.remove(temp_path)
            except OSError:
                pass
        except Exception as exc:
            logging.error(f"Google Cloud TTS synthesis error: {exc}")
            self._play_text_gtts_fallback(text)

    def _play_text_gtts_fallback(self, text: str):
        lang = self.language.split("-")[0] if "-" in self.language else self.language
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
            temp_path = temp_file.name
        try:
            tts_obj = _gTTS(text=text, lang=lang, slow=False)
            tts_obj.save(temp_path)
            logging.info(f"gTTS Fallback: Saved audio for '{text[:40]}...'")
            self._play_audio_file(temp_path)
        except Exception as exc:
            logging.error(f"gTTS synthesis error: {exc}")
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    def _play_audio_file(self, path: str) -> None:
        if os.name == "nt":
            EdgeTTS._play_audio_file_windows(path)
        else:
            EdgeTTS._play_audio_file_linux(path)


def _gemini_tts_instruction(voice_gender: str) -> str:
    if str(voice_gender or "").strip().lower() == "male":
        return (
            "أنت محرك تحويل النص إلى صوت (TTS). مهمتك الوحيدة هي قراءة النص الذي يرسله المستخدم بصوتك المصري. "
            "لا تضيف أي تعليق، لا تجيب على الأسئلة الموجودة في النص، ولا تقول 'حاضر' أو 'النص هو'. "
            "فقط انطق النص المرسل كما هو بالضبط."
        )
    return (
        "أنتِ محرك تحويل نص إلى كلام (TTS). مهمتك هي نطق النص المرسل إليك بصوتك المصري الطبيعي والجذاب. "
        "يجب أن تنطقي النص المرسل كما هو بالضبط دون أي إضافات، تعليقات، أو إجابة على الأسئلة الموجودة فيه."
    )


async def synthesize_gemini_live_pcm(
    *,
    text: str,
    api_key: str,
    voice_gender: str = "female",
    voice_name: str = "",
    model_id: str | None = None,
    timeout_s: float = 30.0,
    on_chunk: callable = None, # Added callback
) -> bytes:
    # Use v1beta for newest models
    client = genai.Client(
        api_key=require_single_gemini_api_key(api_key),
        http_options={'api_version': 'v1beta'}
    )
    audio_bytes = bytearray()
    config = build_live_audio_config(
        system_instruction=_gemini_tts_instruction(voice_gender),
        voice_gender=voice_gender,
        voice_name=voice_name,
        input_transcription=True,
        output_transcription=True,
    )

    resolved_model = resolve_live_model(model_id)
    if not resolved_model.startswith("models/"):
        resolved_model = f"models/{resolved_model}"
        
    try:
        async with client.aio.live.connect(model=resolved_model, config=config) as session:
            # Kickstart with silence at MIC rate (16000 Hz) - this is realtime INPUT, not speaker output
            # 16000 Hz * 0.05s = 800 samples = 1600 bytes
            silence = b'\x00' * 1600
            await session.send_realtime_input(
                audio=types.Blob(data=silence, mime_type="audio/pcm;rate=16000")
            )
            
            # Send the actual text turn
            await session.send(input=text, end_of_turn=True)

            async def receive_all() -> None:
                async for response in session.receive():
                    if response.server_content is not None:
                        model_turn = response.server_content.model_turn
                        if model_turn is not None:
                            for part in model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    chunk = part.inline_data.data
                                    audio_bytes.extend(chunk)
                                    if on_chunk:
                                        on_chunk(chunk) # Play chunk immediately
                        
                        if getattr(response.server_content, "turn_complete", False):
                            break

            await asyncio.wait_for(receive_all(), timeout=timeout_s)

    finally:
        # Properly close the async client to avoid RuntimeWarnings
        await client.aio.aclose()

    return bytes(audio_bytes)


class GeminiTTS(TTSBase):
    """High-quality Arabic TTS using Gemini Live audio with streaming playback."""

    def __init__(self, api_key: str, voice_gender="female", language="ar-EG"):
        self.queue: queue.Queue = queue.Queue()
        self.thread = None
        self.running = False

        self.api_key = require_single_gemini_api_key(api_key) if str(api_key or "").strip() else ""
        self.voice_gender = voice_gender
        self.language = language
        self.model_id = resolve_live_model()
        
        # PyAudio components
        self.p = None
        self.stream = None

    def start(self):
        if self.thread is not None:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("[TTS] Worker thread started", flush=True)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None

    def say(self, text: str):
        if not self.api_key:
            print(f"[TTS ERROR] Gemini TTS: No API key provided!", flush=True)
            return
        
        # Ensure we are using the full model name
        model_to_use = self.model_id
        if not model_to_use.startswith("models/"):
            model_to_use = f"models/{model_to_use}"
            
        print(f"[TTS] Queued for {model_to_use}: '{text[:60]}'...", flush=True)
        self.queue.put(text)

    def _run_loop(self):
        # Initialize PyAudio
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True
        )
        
        logging.info(f"Gemini TTS started (gender={self.voice_gender})")
        while self.running:
            try:
                text = self.queue.get(timeout=0.5)
                if text:
                    self._play_text(text)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Error in GeminiTTS loop: {e}")
        
        # Cleanup PyAudio
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception: pass
        if self.p:
            try:
                self.p.terminate()
            except Exception: pass

    def _play_text(self, text: str):
        # Text normalization
        text = text.replace("Aria", "أريا").replace("aria", "أريا")

        model_id = self.model_id
        gender = self.voice_gender.lower()
        if gender == "both":
            import random
            gender = random.choice(["male", "female"])

        VOICE_MAP = {
            "female": "Kore",
            "male": "Charon",
        }
        chosen_voice = VOICE_MAP.get(gender, "Kore")
        
        logging.info(f"Gemini TTS: voice={chosen_voice} ({gender}), streaming to speaker")

        def chunk_callback(chunk):
            if self.stream:
                try:
                    self.stream.write(chunk)
                except Exception: pass

        try:
            asyncio.run(
                synthesize_gemini_live_pcm(
                    text=text,
                    api_key=self.api_key,
                    voice_gender=gender,
                    voice_name=chosen_voice,
                    model_id=model_id,
                    timeout_s=30.0,
                    on_chunk=chunk_callback # Pass the streaming callback
                )
            )
        except Exception as e:
            print(f"[TTS ERROR] Streaming error: {e}", flush=True)
            logging.error(f"Streaming error in GeminiTTS: {e}")

    def _play_pcm(self, audio_data: bytes):
        if self.stream:
            try:
                self.stream.write(audio_data)
            except Exception: pass

    def _play_audio_file(self, path: str) -> None:
        if os.name == "nt":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            try:
                import soundfile as sf  # type: ignore
                import sounddevice as sd  # type: ignore
                data, sr = sf.read(path, dtype="float32")
                sd.play(data, sr)
                sd.wait()
            except Exception as e:
                print(f"[TTS ERROR] Audio playback failed: {e}", flush=True)
                logging.error(f"Gemini TTS: audio playback failed: {e}")


class ChatterboxHttpTTS(TTSBase):
    def __init__(
        self,
        base_url: str,
        voice_gender="female",
        language="ar-EG",
        voice_uri="",
        voice_mode="predefined",
        reference_audio="",
        tts_rate=1.0,
    ):
        self.queue: queue.Queue = queue.Queue()
        self.thread = None
        self.running = False
        self.base_url = base_url
        self.voice_gender = voice_gender
        self.language = language
        self.voice_uri = voice_uri
        self.voice_mode = voice_mode
        self.reference_audio = reference_audio
        self.tts_rate = tts_rate

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def say(self, text: str):
        self.queue.put(text)

    def _run_loop(self):
        while self.running:
            try:
                text = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            prepared = normalize_tts_text(text, language=self.language)
            if not prepared:
                continue

            try:
                self._play_text(prepared)
            except Exception as exc:
                logging.error(f"Chatterbox TTS playback failed: {exc}")

    def _play_text(self, text: str):
        audio_bytes, fmt, _meta = asyncio.run(
            synthesize_with_chatterbox(
                text=text,
                base_url=self.base_url,
                language=self.language,
                voice_gender=self.voice_gender,
                voice_mode=self.voice_mode,
                reference_audio=self.reference_audio,
                voice_uri=self.voice_uri,
                speed_factor=self.tts_rate,
                output_format="mp3",
            )
        )

        suffix = ".wav" if fmt == "wav" else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
            temp_path = temp_file.name
            temp_file.write(audio_bytes)

        try:
            if fmt == "wav":
                self._play_audio_file_wav(temp_path)
            else:
                EdgeTTS._play_audio_file_windows(temp_path)
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    @staticmethod
    def _play_audio_file_wav(path: str) -> None:
        if os.name == "nt":
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        raise RuntimeError("Chatterbox local playback is only implemented for Windows hosts")


class Pyttsx3TTS(TTSBase):
    def __init__(self, voice_gender="female", language="en"):
        self.queue: queue.Queue = queue.Queue()
        self.thread = None
        self.running = False
        self.engine = None
        self.voice_gender = voice_gender
        self.language = language

    def start(self):
        if not TTS_AVAILABLE:
            return
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            # We can't really force stop pyttsx3 runLoop easily without getting stuck
            # But we can clear queue and hope current utterance finishes
            pass

    def say(self, text: str):
        if not TTS_AVAILABLE:
            logging.info(f"TTS (Mock): {text}")
            return
        self.queue.put(normalize_tts_text(text, language=self.language))

    def _run_loop(self):
        # pyttsx3 engine must be initialized in the same thread it runs
        try:
            self.engine = pyttsx3.init()
            self._configure_voice()
        except Exception as e:
            logging.error(f"Failed to init pyttsx3: {e}")
            return

        while self.running:
            try:
                # Get text with timeout to allow checking self.running
                text = self.queue.get(timeout=0.5)
                logging.info(f"TTS saying: {text}")
                self.engine.say(text)
                self.engine.runAndWait()
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"TTS error: {e}")

    def _configure_voice(self):
        # Very basic voice selection logic
        voices = self.engine.getProperty('voices')
        selected = None
        for v in voices:
            # Try to match gender/language if possible
            # Windows/Linux voices vary wildly in metadata
            if self.voice_gender in v.name.lower():
                selected = v
                break
        
        if selected:
            self.engine.setProperty('voice', selected.id)


class XttsTTS(TTSBase):
    """
    TTS provider using fine-tuned XTTS model.
    Generates natural Arabic speech using the trained voice.
    """

    def __init__(
        self,
        base_dir: str = "XTTS_v2_base",
        checkpoint_path: str = "",
        speaker_wav: str = "source_audio/egyptian_voice.wav",
        language: str = "ar",
        cache_dir: str = "./config/data/tts_cache",
        device: str = "",
    ):
        self.base_dir = base_dir
        self.checkpoint_path = checkpoint_path
        self.speaker_wav = speaker_wav
        self.language = language
        self.cache_dir = cache_dir
        self.device = device
        self.model = None
        self._queue: queue.Queue = queue.Queue()
        self._thread = None
        self._running = False
        self._cache: dict[str, str] = {}  # text -> wav_path

    def start(self):
        if self._running:
            return
        self._running = True
        os.makedirs(self.cache_dir, exist_ok=True)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def say(self, text: str):
        if self.model is None and not self._running:
            logging.info(f"XTTS TTS (not loaded): {text}")
            return
        self._queue.put(normalize_tts_text(text, language=self.language))

    def _load_model(self):
        """Load XTTS model (must be called from worker thread)"""
        try:
            import torch  # type: ignore
            import torchaudio  # type: ignore
            import soundfile as sf  # type: ignore

            # Apply soundfile patch for Windows
            def patched_load(uri, **kwargs):
                try:
                    data, sr = sf.read(uri, dtype='float32')
                    if data.ndim == 1:
                        tensor = torch.from_numpy(data).unsqueeze(0)
                    else:
                        tensor = torch.from_numpy(data).t().contiguous()
                    return tensor, sr
                except Exception:
                    return torch.zeros(1, 22050), 22050

            torchaudio.load = patched_load

            from TTS.tts.configs.xtts_config import XttsConfig  # type: ignore
            from TTS.tts.models.xtts import Xtts  # type: ignore

            device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")

            logging.info(f"XTTS: Loading base model from {self.base_dir}...")
            config = XttsConfig()
            config.load_json(os.path.join(self.base_dir, "config.json"))
            model = Xtts.init_from_config(config)
            model.load_checkpoint(config, checkpoint_dir=self.base_dir, eval=True, strict=False)

            # Load fine-tuned weights if available
            ckpt = self.checkpoint_path
            if not ckpt:
                ckpt = self._find_best_checkpoint()
            if ckpt and os.path.exists(ckpt):
                logging.info(f"XTTS: Loading fine-tuned weights from {ckpt}")
                state_dict = torch.load(ckpt, map_location=device)

                # Auto-detect: full model vs GPT-only
                sample_key = next(iter(state_dict.keys()), "")
                is_full_model = sample_key.startswith("gpt.") or sample_key.startswith("mel_stats")

                if is_full_model:
                    model.load_state_dict(state_dict, strict=False)
                else:
                    model.gpt.load_state_dict(state_dict, strict=False)

            model.to(device)
            model.eval()
            self.model = model
            logging.info("XTTS: Model loaded and ready!")

        except Exception as e:
            logging.error(f"XTTS: Failed to load model: {e}")
            self.model = None

    def _find_best_checkpoint(self) -> str:
        """Auto-find the best available checkpoint"""
        best, best_epoch = None, -1
        for d in ["run/manual_training", "run/training_output"]:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if not f.endswith(".pth"):
                    continue
                for prefix in ["checkpoint_epoch_", "xtts_epoch_"]:
                    if f.startswith(prefix):
                        try:
                            n = int(f[len(prefix):].replace(".pth", ""))
                            if n > best_epoch:
                                best_epoch = n
                                best = os.path.join(d, f)
                        except ValueError:
                            pass
        return best or ""

    def _run_loop(self):
        """Worker thread: load model then process TTS queue"""
        self._load_model()

        if self.model is None:
            logging.error("XTTS: Model failed to load. Falling back to logging.")
            while self._running:
                try:
                    text = self._queue.get(timeout=0.5)
                    logging.info(f"XTTS TTS (no model): {text}")
                except queue.Empty:
                    continue
            return

        import soundfile as sf  # type: ignore

        while self._running:
            try:
                text = self._queue.get(timeout=0.5)
                logging.info(f"XTTS saying: {text}")
                text_processed = text

                # Check cache (use processed text for cache key to distinguish pronunciation)
                if text_processed in self._cache and os.path.exists(self._cache[text_processed]):
                    self._play_wav(self._cache[text_processed])
                    continue

                # Generate speech
                import torch  # type: ignore
                with torch.no_grad():
                    output = self.model.synthesize(
                        text=text_processed,
                        config=self.model.config,
                        speaker_wav=self.speaker_wav,
                        language=self.language,
                        temperature=0.6,       # Lower temp for better stability with diacritics
                        repetition_penalty=6.0, # Higher penalty to avoid stutter
                        top_k=50,
                        top_p=0.85,
                    )

                wav = output["wav"]
                sr = self.model.config.model_args.output_sample_rate

                # Save to cache
                safe_name = "".join(c if c.isalnum() else "_" for c in text[:50])
                cache_path = os.path.join(self.cache_dir, f"xtts_{safe_name}_{hash(text_processed) & 0xFFFFFF:06x}.wav")
                sf.write(cache_path, wav, sr)
                self._cache[text_processed] = cache_path

                self._play_wav(cache_path)

            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"XTTS TTS error: {e}")

    def _play_wav(self, path: str):
        """Play a WAV file through sounddevice"""
        try:
            import soundfile as sf  # type: ignore
            import sounddevice as sd  # type: ignore
            data, sr = sf.read(path, dtype='float32')
            sd.play(data, sr)
            sd.wait()
        except ImportError:
            logging.warning("sounddevice not available — can't play audio. File saved at: " + path)
        except Exception as e:
            logging.error(f"XTTS: Failed to play {path}: {e}")

class PiperTTS(TTSBase):
    """
    Ultra-fast TTS provider using Piper (Excellent for Raspberry Pi / Zero-Resource).
    Requires 'piper-tts' pip package and an onnx model (e.g. ar-AR model).
    """

    def __init__(
        self,
        model_path: str = "./config/models/piper/ar_JO-kareem-low.onnx",
        cache_dir: str = "./config/data/tts_cache",
        language: str = "ar"
    ):
        self.model_path = model_path
        self.config_path = model_path + ".json"
        self.cache_dir = cache_dir
        self.language = language
        self.voice = None
        self._queue: queue.Queue = queue.Queue()
        self._thread = None
        self._running = False
        self._cache: dict[str, str] = {}

    def start(self):
        if self._running:
            return
        if not PIPER_AVAILABLE:
            logging.error("PiperTTS requires 'piper-tts' to be installed.")
            return
            
        self._running = True
        os.makedirs(self.cache_dir, exist_ok=True)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def say(self, text: str):
        if self.voice is None and not self._running:
            logging.info(f"Piper TTS (not loaded): {text}")
            return
        self._queue.put(normalize_tts_text(text, language=self.language))

    def _run_loop(self):
        try:
            self.voice = PiperVoice.load(self.model_path, config_path=self.config_path)
            logging.info(f"Piper TTS: Model loaded from {self.model_path}")
        except Exception as e:
            logging.error(f"Piper TTS: Failed to load model: {e}")
            self.voice = None

        if self.voice is None:
            logging.error("Piper TTS: Model failed to load. Falling back to logging.")
            while self._running:
                try:
                    text = self._queue.get(timeout=0.5)
                    logging.info(f"Piper TTS (no model): {text}")
                except queue.Empty:
                    continue
            return

        import wave
        while self._running:
            try:
                text = self._queue.get(timeout=0.5)
                logging.info(f"Piper saying: {text}")
                text_processed = text

                if text_processed in self._cache and os.path.exists(self._cache[text_processed]):
                    self._play_wav(self._cache[text_processed])
                    continue

                safe_name = "".join(c if c.isalnum() else "_" for c in text[:50])
                cache_path = os.path.join(self.cache_dir, f"piper_{safe_name}_{hash(text_processed) & 0xFFFFFF:06x}.wav")
                
                with wave.open(cache_path, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(self.voice.config.sample_rate)
                    self.voice.synthesize(text_processed, wav_file)

                self._cache[text_processed] = cache_path
                self._play_wav(cache_path)

            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Piper TTS error: {e}")

    def _play_wav(self, path: str):
        try:
            import soundfile as sf  # type: ignore
            import sounddevice as sd  # type: ignore
            data, sr = sf.read(path, dtype='float32')
            sd.play(data, sr)
            sd.wait()
        except ImportError:
            logging.warning("sounddevice not available — can't play audio.")
        except Exception as e:
            logging.error(f"Piper TTS: Failed to play {path}: {e}")


def build_tts(provider: str, **kwargs) -> TTSBase:
    """
    Factory: creates a Gemini TTS provider.
    Offline TTS (Piper, Edge, XTTS) are bypassed — only Gemini Studio API.
    """
    voice_gender = kwargs.get("voice_gender", "female").lower()
    language = kwargs.get("language", "ar-EG")
    api_key = kwargs.get("gemini_api_key", "")
    
    logging.info(f"TTS Engine: Gemini Studio (keys={'yes' if api_key else 'NONE'}, lang={language})")
    return GeminiTTS(
        api_key=api_key,
        voice_gender=voice_gender,
        language=language
    )
