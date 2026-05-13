import os
from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from urllib.parse import urlparse
from pathlib import Path
from dotenv import load_dotenv  # type: ignore

# Find project root (one level up from brain/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / "config" / ".env", override=True)


def normalize_chatterbox_voice_mode(value: object, default: str = "predefined") -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "clone":
        return "clone"
    return default


@dataclass(frozen=True)
class BrainConfig:
    log_level: str = "INFO"
    transport: str = "mock"

    esp32_tcp_host: str = "127.0.0.1"
    esp32_tcp_port: int = 8765
    esp32_serial_port: str = ""
    esp32_serial_baud: int = 115200

    memory_db_path: str = "./config/data/brain.sqlite"

    wake_word: str = "aria"
    sleep_timeout_s: float = 20.0

    vosk_model_path: str = ""

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    ollama_cloud_url: str = ""
    ollama_cloud_model: str = ""
    llm_device: str = "cpu"
    
    vlm_base_url: str = "http://127.0.0.1:11434"
    vlm_model: str = "qwen3-vl:8b"
    vlm_cloud_url: str = ""
    vlm_cloud_model: str = ""
    vlm_online_enabled: bool = False
    vlm_device: str = "gpu"

    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    openai_api_key: str = ""
    google_api_key: str = ""
    vision_api_key: str = ""
    gemini_model: str = ""
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    hf_api_key: str = ""
    hf_model: str = ""
    hf_keys_file: str = "./config/data/hf_keys.json"

    settings_path: str = "./config/data/robot_settings.json"
    allowed_topics: tuple[str, ...] = field(default_factory=tuple)
    robot_language: str = "ar-EG"
    stt_provider: str = "gemini_live"
    stt_online_enabled: bool = True
    tts_lang: str = "ar-EG"
    tts_voice_gender: str = "female"
    tts_provider: str = "gemini"
    tts_online_enabled: bool = True
    chatterbox_base_url: str = "http://127.0.0.1:8004"
    chatterbox_voice_mode: str = "predefined"
    chatterbox_reference_audio: str = ""
    tts_cache_dir: str = "./config/data/tts_cache"
    tts_voice_uri: str = ""
    tts_rate: float = 1.0
    xtts_base_dir: str = "XTTS_v2_base"
    xtts_checkpoint: str = ""
    xtts_speaker_wav: str = "source_audio/egyptian_voice.wav"
    gesture_detection_enabled: bool = True
    gesture_bindings: dict[str, str] = field(default_factory=dict)
    camera_resolution: str = "640x480"
    camera_fps: int = 90

    # Safety & Heartbeat
    heartbeat_interval_ms: int = 500
    heartbeat_timeout_ms: int = 2000
    default_speed_limit: float = 0.5
    
    # Thermal
    thermal_monitor_interval_s: float = 2.0
    thermal_warm_threshold_c: float = 60.0
    thermal_hot_threshold_c: float = 70.0
    thermal_critical_threshold_c: float = 80.0
    
    # Performance knobs
    perf_frame_skip: int = 1  # process every frame (cloud VLM handles the load)
    perf_mediapipe_schedule: tuple[str, ...] = ("face", "hands", "pose")  # Removed "idle" for faster processing
    perf_resolution: str = "640x480"
    perf_audio_window_ms: int = 250
    perf_audio_period_ms: int = 1000
    perf_vlm_on_transition: bool = True
    perf_vlm_on_scene_change: bool = True
    perf_vlm_on_ambiguous: bool = True

    @staticmethod
    def _parse_int(name: str, default: int, *, min_v: int | None = None, max_v: int | None = None) -> int:
        raw = os.getenv(name, "")
        try:
            v = int(raw) if raw.strip() else default
        except Exception:
            v = default
        if min_v is not None and v < min_v:
            return default
        if max_v is not None and v > max_v:
            return default
        return v

    @staticmethod
    def _parse_float(name: str, default: float, *, min_v: float | None = None, max_v: float | None = None) -> float:
        raw = os.getenv(name, "")
        try:
            v = float(raw) if raw.strip() else default
        except Exception:
            v = default
        if min_v is not None and v < min_v:
            return default
        if max_v is not None and v > max_v:
            return default
        return v

    @staticmethod
    def _validate_http_url(name: str, default: str) -> str:
        raw = os.getenv(name, default).strip() or default
        try:
            u = urlparse(raw)
            if u.scheme not in ("http", "https"):
                return default
            if not u.netloc:
                return default
            return raw.rstrip("/")
        except Exception:
            return default

    @staticmethod
    def _parse_device(name: str, default: str) -> str:
        raw = os.getenv(name, default).strip().lower()
        if raw == "gpu":
            return "gpu"
        if raw == "cpu":
            return "cpu"
        return default

    @staticmethod
    def _single_secret(name: str) -> str:
        raw = os.getenv(name, "").strip()
        if not raw:
            return ""
        if "," in raw:
            raise ValueError(f"{name} must contain one fixed key only, not a comma-separated key list.")
        return raw

    @staticmethod
    def from_env() -> "BrainConfig":
        allowed_topics_raw = os.getenv("BRAIN_ALLOWED_TOPICS", "")
        allowed_topics = tuple(x.strip() for x in allowed_topics_raw.split(",") if x.strip()) if allowed_topics_raw else tuple()
        return BrainConfig(
            log_level=os.getenv("BRAIN_LOG_LEVEL", "INFO"),
            transport=os.getenv("BRAIN_TRANSPORT", "mock"),
            esp32_tcp_host=os.getenv("BRAIN_ESP32_TCP_HOST", "127.0.0.1"),
            esp32_tcp_port=BrainConfig._parse_int("BRAIN_ESP32_TCP_PORT", 8765, min_v=1, max_v=65535),
            esp32_serial_port=os.getenv("BRAIN_ESP32_SERIAL_PORT", ""),
            esp32_serial_baud=BrainConfig._parse_int("BRAIN_ESP32_SERIAL_BAUD", 115200, min_v=1200, max_v=2_000_000),
            memory_db_path=os.getenv("BRAIN_MEMORY_DB_PATH", "./data/brain.sqlite"),
            wake_word=os.getenv("BRAIN_WAKE_WORD", "aria"),
            sleep_timeout_s=BrainConfig._parse_float("BRAIN_SLEEP_TIMEOUT_S", 20.0, min_v=1.0, max_v=3600.0),
            vosk_model_path=os.getenv("BRAIN_VOSK_MODEL_PATH", ""),
            ollama_base_url=BrainConfig._validate_http_url("BRAIN_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("BRAIN_OLLAMA_MODEL", ""),
            ollama_cloud_url=BrainConfig._validate_http_url("BRAIN_OLLAMA_CLOUD_URL", ""),
            ollama_cloud_model=os.getenv("BRAIN_OLLAMA_CLOUD_MODEL", ""),
            llm_device=BrainConfig._parse_device("BRAIN_LLM_DEVICE", "cpu"),
            vlm_base_url=BrainConfig._validate_http_url("BRAIN_VLM_BASE_URL", "http://127.0.0.1:11434"),
            vlm_model=os.getenv("BRAIN_VLM_MODEL", "qwen3-vl:8b"),
            vlm_cloud_url=BrainConfig._validate_http_url("BRAIN_VLM_CLOUD_URL", ""),
            vlm_cloud_model=os.getenv("BRAIN_VLM_CLOUD_MODEL", ""),
            vlm_online_enabled=os.getenv("BRAIN_VLM_ONLINE", "false").lower() in ("1", "true", "yes", "on"),
            vlm_device=BrainConfig._parse_device("BRAIN_VLM_DEVICE", "gpu"),
            openai_base_url=BrainConfig._validate_http_url("BRAIN_OPENAI_BASE_URL", "https://api.openai.com/v1"),
            openai_model=os.getenv("BRAIN_OPENAI_MODEL", "gpt-4o-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            google_api_key=BrainConfig._single_secret("BRAIN_GEMINI_API_KEY"),
            vision_api_key=os.getenv("BRAIN_VISION_API_KEY", ""),
            gemini_model=os.getenv("BRAIN_GEMINI_MODEL", "gemini-1.5-flash"),
            gemini_live_model=os.getenv("BRAIN_GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview"),
            hf_api_key=os.getenv("BRAIN_HF_API_KEY", ""),
            hf_model=os.getenv("BRAIN_HF_MODEL", "moonshotai/Kimi-K2.6:fastest"),
            hf_keys_file=os.getenv("BRAIN_HF_KEYS_FILE", "./config/data/hf_keys.json"),
            settings_path=os.getenv("BRAIN_SETTINGS_PATH", "./data/robot_settings.json"),
            allowed_topics=allowed_topics,
            robot_language=os.getenv("BRAIN_ROBOT_LANGUAGE", "ar-EG"),
            stt_provider=os.getenv("BRAIN_STT_PROVIDER", "gemini_live"),
            stt_online_enabled=os.getenv("BRAIN_STT_ONLINE", "true").lower() in ("1", "true", "yes", "on"),
            tts_lang=os.getenv("BRAIN_TTS_LANG", "ar-EG"),
            tts_voice_gender=os.getenv("BRAIN_TTS_VOICE_GENDER", "female"),
            tts_provider=os.getenv("BRAIN_TTS_PROVIDER", "gemini"),
            tts_online_enabled=os.getenv("BRAIN_TTS_ONLINE", "true").lower() in ("1", "true", "yes", "on"),
            chatterbox_base_url=BrainConfig._validate_http_url("BRAIN_CHATTERBOX_BASE_URL", "http://127.0.0.1:8004"),
            chatterbox_voice_mode=normalize_chatterbox_voice_mode(
                os.getenv("BRAIN_CHATTERBOX_VOICE_MODE", "predefined"),
            ),
            chatterbox_reference_audio=os.getenv("BRAIN_CHATTERBOX_REFERENCE_AUDIO", ""),
            tts_cache_dir=os.getenv("BRAIN_TTS_CACHE_DIR", "./data/tts_cache"),
            tts_voice_uri=os.getenv("BRAIN_TTS_VOICE_URI", ""),
            tts_rate=BrainConfig._parse_float("BRAIN_TTS_RATE", 1.0, min_v=0.6, max_v=1.5),
            xtts_base_dir=os.getenv("BRAIN_XTTS_BASE_DIR", "XTTS_v2_base"),
            xtts_checkpoint=os.getenv("BRAIN_XTTS_CHECKPOINT", ""),
            xtts_speaker_wav=os.getenv("BRAIN_XTTS_SPEAKER_WAV", "source_audio/egyptian_voice.wav"),
            
            # Safety checks
            heartbeat_interval_ms=int(os.getenv("HEARTBEAT_INTERVAL_MS", "500")),
            heartbeat_timeout_ms=int(os.getenv("HEARTBEAT_TIMEOUT_MS", "2000")),
            default_speed_limit=float(os.getenv("DEFAULT_SPEED_LIMIT", "0.5")),
            
            thermal_monitor_interval_s=float(os.getenv("THERMAL_MONITOR_INTERVAL_S", "2.0")),
            thermal_warm_threshold_c=float(os.getenv("THERMAL_WARM_THRESHOLD_C", "60.0")),
            thermal_hot_threshold_c=float(os.getenv("THERMAL_HOT_THRESHOLD_C", "70.0")),
            thermal_critical_threshold_c=float(os.getenv("THERMAL_CRITICAL_THRESHOLD_C", "80.0")),
            
            # Performance knobs
            perf_frame_skip=BrainConfig._parse_int("PERF_FRAME_SKIP", 1, min_v=0, max_v=10),
            perf_mediapipe_schedule=tuple(x.strip() for x in os.getenv("PERF_MEDIAPIPE_SCHEDULE", "face,hands,pose,idle").split(",") if x.strip()),
            perf_resolution=os.getenv("PERF_RESOLUTION", "640x480"),
            perf_audio_window_ms=BrainConfig._parse_int("PERF_AUDIO_WINDOW_MS", 250, min_v=50, max_v=1000),
            perf_audio_period_ms=BrainConfig._parse_int("PERF_AUDIO_PERIOD_MS", 1000, min_v=200, max_v=5000),
            perf_vlm_on_transition=os.getenv("PERF_VLM_ON_TRANSITION", "true").lower() in ("1", "true", "yes", "on"),
            perf_vlm_on_scene_change=os.getenv("PERF_VLM_ON_SCENE_CHANGE", "true").lower() in ("1", "true", "yes", "on"),
            perf_vlm_on_ambiguous=os.getenv("PERF_VLM_ON_AMBIGUOUS", "true").lower() in ("1", "true", "yes", "on"),
        )


    def with_ollama_model(self, model: str | None) -> "BrainConfig":
        return replace(self, ollama_model=model or "")
    
    def with_vlm_model(self, model: str | None) -> "BrainConfig":
        return replace(self, vlm_model=model or "")

    def with_robot_settings(self, settings: dict) -> "BrainConfig":
        allowed = settings.get("allowedTopics")
        if isinstance(allowed, list):
            allowed_topics = tuple(str(x).strip() for x in allowed if str(x).strip())
        elif isinstance(allowed, str):
            allowed_topics = tuple(x.strip() for x in allowed.split(",") if x.strip())
        else:
            allowed_topics = self.allowed_topics

        ollama_base_url = settings.get("ollamaBaseUrl")
        ollama_model = settings.get("ollamaModel")
        llm_device = settings.get("llmDevice")
        
        vlm_base_url = settings.get("vlmBaseUrl")
        vlm_model = settings.get("vlmModel")
        vlm_cloud_url = settings.get("vlmCloudUrl")
        vlm_cloud_model = settings.get("vlmCloudModel")
        vlm_online_raw = settings.get("vlmOnline")
        vlm_device = settings.get("vlmDevice")
        
        robot_language = settings.get("robotLanguage")
        stt_provider = settings.get("sttProvider")
        stt_online_raw = settings.get("sttOnline")
        tts_voice_gender = settings.get("ttsVoiceGender")
        tts_provider = settings.get("ttsProvider")
        tts_online_raw = settings.get("ttsOnline")
        chatterbox_base_url = settings.get("chatterboxBaseUrl")
        chatterbox_voice_mode = settings.get("chatterboxVoiceMode")
        chatterbox_reference_audio = settings.get("chatterboxReferenceAudio")
        tts_cache_dir = settings.get("ttsCacheDir")
        tts_lang = settings.get("ttsLang")
        tts_voice_uri = settings.get("ttsVoiceURI")
        tts_rate_raw = settings.get("ttsRate")
        gesture_detection_enabled_raw = settings.get("gestureDetectionEnabled")
        gesture_bindings_raw = settings.get("gestureBindings")
        camera_resolution = settings.get("cameraResolution")
        camera_fps_raw = settings.get("cameraFps")

        stt_online_enabled = self.stt_online_enabled
        if isinstance(stt_online_raw, bool):
            stt_online_enabled = stt_online_raw

        tts_online_enabled = self.tts_online_enabled
        if isinstance(tts_online_raw, bool):
            tts_online_enabled = tts_online_raw

        vlm_online_enabled = self.vlm_online_enabled
        if isinstance(vlm_online_raw, bool):
            vlm_online_enabled = vlm_online_raw

        gesture_detection_enabled = self.gesture_detection_enabled
        if isinstance(gesture_detection_enabled_raw, bool):
            gesture_detection_enabled = gesture_detection_enabled_raw

        gesture_bindings = self.gesture_bindings
        if isinstance(gesture_bindings_raw, dict):
            out: dict[str, str] = {}
            for k, v in gesture_bindings_raw.items():
                key = str(k).strip().lower()
                val = str(v).strip()
                if key and val:
                    out[key] = val
            gesture_bindings = out

        camera_fps = self.camera_fps
        try:
            camera_fps = int(camera_fps_raw) if camera_fps_raw is not None else camera_fps
        except Exception:
            camera_fps = self.camera_fps
        if camera_fps < 1 or camera_fps > 120:
            camera_fps = self.camera_fps

        tts_rate = self.tts_rate
        try:
            tts_rate = float(tts_rate_raw) if tts_rate_raw is not None else tts_rate
        except Exception:
            tts_rate = self.tts_rate
        if tts_rate < 0.6 or tts_rate > 1.5:
            tts_rate = self.tts_rate

        return replace(
            self,
            ollama_base_url=str(ollama_base_url).strip() if isinstance(ollama_base_url, str) and ollama_base_url.strip() else self.ollama_base_url,
            ollama_model=str(ollama_model).strip() if isinstance(ollama_model, str) and ollama_model.strip() else self.ollama_model,
            llm_device="gpu" if str(llm_device).strip().lower() == "gpu" else "cpu",
            vlm_base_url=str(vlm_base_url).strip() if isinstance(vlm_base_url, str) and vlm_base_url.strip() else self.vlm_base_url,
            vlm_model=str(vlm_model).strip() if isinstance(vlm_model, str) and vlm_model.strip() else self.vlm_model,
            vlm_cloud_url=str(vlm_cloud_url).strip() if isinstance(vlm_cloud_url, str) and vlm_cloud_url.strip() else self.vlm_cloud_url,
            vlm_cloud_model=str(vlm_cloud_model).strip() if isinstance(vlm_cloud_model, str) and vlm_cloud_model.strip() else self.vlm_cloud_model,
            vlm_online_enabled=vlm_online_enabled,
            vlm_device="cpu" if str(vlm_device).strip().lower() == "cpu" else "gpu",
            allowed_topics=allowed_topics,
            robot_language=str(robot_language).strip() if isinstance(robot_language, str) and robot_language.strip() else self.robot_language,
            stt_provider=str(stt_provider).strip() if isinstance(stt_provider, str) and str(stt_provider).strip() else self.stt_provider,
            stt_online_enabled=stt_online_enabled,
            tts_lang=str(tts_lang).strip() if isinstance(tts_lang, str) and str(tts_lang).strip() else self.tts_lang,
            tts_voice_gender=str(tts_voice_gender).strip() if isinstance(tts_voice_gender, str) and str(tts_voice_gender).strip() else self.tts_voice_gender,
            tts_provider=str(tts_provider).strip() if isinstance(tts_provider, str) and str(tts_provider).strip() else self.tts_provider,
            tts_online_enabled=tts_online_enabled,
            chatterbox_base_url=str(chatterbox_base_url).strip() if isinstance(chatterbox_base_url, str) and str(chatterbox_base_url).strip() else self.chatterbox_base_url,
            chatterbox_voice_mode=normalize_chatterbox_voice_mode(chatterbox_voice_mode, self.chatterbox_voice_mode),
            chatterbox_reference_audio=(
                str(chatterbox_reference_audio).strip()
                if isinstance(chatterbox_reference_audio, str)
                else self.chatterbox_reference_audio
            ),
            tts_cache_dir=str(tts_cache_dir).strip() if isinstance(tts_cache_dir, str) and str(tts_cache_dir).strip() else self.tts_cache_dir,
            tts_voice_uri=str(tts_voice_uri).strip() if isinstance(tts_voice_uri, str) and str(tts_voice_uri).strip() else self.tts_voice_uri,
            tts_rate=tts_rate,
            gesture_detection_enabled=gesture_detection_enabled,
            gesture_bindings=gesture_bindings,
            camera_resolution=str(camera_resolution).strip() if isinstance(camera_resolution, str) and camera_resolution.strip() else self.camera_resolution,
            camera_fps=camera_fps,
        )
