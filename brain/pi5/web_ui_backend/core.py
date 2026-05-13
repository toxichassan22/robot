import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, Field, field_validator

try:
    from brain.state.robot_state_manager import RobotMode, RobotStateManager
except ImportError:
    RobotMode = Any
    RobotStateManager = Any

from .runtime_paths import get_app_root


REPO_ROOT = get_app_root(__file__, depth=4)
# Load environment variables from config/.env
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / "config" / ".env")

DATA_DIR = REPO_ROOT / "config" / "data"
DEFAULT_SETTINGS_PATH = DATA_DIR / "robot_settings.json"
DEFAULT_MEMORY_DB_PATH = DATA_DIR / "brain.sqlite"
DEFAULT_MOTION_LOG_PATH = DATA_DIR / "motion_commands.jsonl"
DEBUG_LLM_PATH = REPO_ROOT / "debug_llm.txt"

app = FastAPI(title="Robot Web UI Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


# -- Debug Snapshot for Live Dashboard --
def get_runtime_debug_snapshot():
    return getattr(app.state, "runtime_debug_snapshot", {})

def set_runtime_debug_snapshot(payload):
    app.state.runtime_debug_snapshot = payload

def set_debug_camera_frame_provider(provider):
    app.state.debug_camera_frame_provider = provider

def set_debug_vision_describe_provider(provider):
    app.state.debug_vision_describe_provider = provider


SETTINGS_PATH = os.getenv("ROBOT_SETTINGS_PATH", str(DEFAULT_SETTINGS_PATH))
MEMORY_DB_PATH = os.getenv("BRAIN_MEMORY_DB_PATH", str(DEFAULT_MEMORY_DB_PATH))
MOTION_LOG_PATH = os.getenv("ROBOT_MOTION_LOG_PATH", str(DEFAULT_MOTION_LOG_PATH))
PIN_BOOTSTRAP = os.getenv("ROBOT_SETTINGS_PIN", "").strip()
PIN_BOOTSTRAP_HASH = os.getenv("ROBOT_SETTINGS_PIN_HASH", "").strip()
SESSION_DURATION = 3600

PIN_HEADER = "x-robot-pin"
PIN_MIN_LEN = 4
PIN_MAX_LEN = 6
PIN_FAIL_WINDOW_S = 300.0
PIN_MAX_FAILS = 5
PIN_LOCKOUT_S = 45.0

sessions: Dict[str, float] = {}
rate_limit: Dict[str, Dict[str, float]] = {}
COMMAND_QUEUE: Optional[asyncio.Queue] = None
STATE_MANAGER: Optional[RobotStateManager] = None
SAFETY_EVENTS: List[Dict[str, Any]] = []
MAX_SAFETY_EVENTS = 50
SERVER_STARTED_AT_S = time.time()
DEFAULT_LLM_DEVICE = "cpu"
DEFAULT_VLM_DEVICE = "gpu"
CURRENT_SETTINGS_VERSION = 5


def normalize_execution_device(value: Any, *, default: str) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "gpu":
        return "gpu"
    if candidate == "cpu":
        return "cpu"
    return default


def num_gpu_for_device(value: Any, *, default: str) -> int:
    return -1 if normalize_execution_device(value, default=default) == "gpu" else 0


def normalize_chatterbox_voice_mode(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "clone":
        return "clone"
    return "predefined"


class RobotSettings(BaseModel):
    version: int = CURRENT_SETTINGS_VERSION
    updatedAtMs: int = 0
    provider: str = "ollama"
    allowedTopics: List[str] = []
    robotLanguage: str = "ar-EG"
    sttLang: str = "ar-EG"
    ttsLang: str = "ar-EG"
    ttsVoiceGender: str = "female"
    ttsProvider: str = "gemini"
    chatterboxBaseUrl: str = "http://127.0.0.1:8004"
    chatterboxInstallDir: str = ""
    chatterboxVoiceMode: str = "predefined"
    chatterboxReferenceAudio: str = ""
    ttsCacheDir: str = "./data/tts_cache"
    ttsVoiceURI: str = ""
    ttsRate: float = 1.0
    gestureDetectionEnabled: bool = True
    cameraResolution: str = "640x480"
    cameraFps: int = 15
    gestureBindings: Dict[str, str] = {}
    ollamaBaseUrl: str = os.getenv("BRAIN_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollamaModel: str = os.getenv("BRAIN_OLLAMA_MODEL", "mistral:latest")
    ollamaCloudUrl: str = os.getenv("BRAIN_OLLAMA_CLOUD_URL", "")
    ollamaCloudModel: str = os.getenv("BRAIN_OLLAMA_CLOUD_MODEL", "")
    llmDevice: str = os.getenv("BRAIN_LLM_DEVICE", DEFAULT_LLM_DEVICE)
    vlmBaseUrl: str = os.getenv("BRAIN_VLM_BASE_URL", "http://127.0.0.1:11434")
    vlmModel: str = os.getenv("BRAIN_VLM_MODEL", "qwen3-vl:8b")
    vlmCloudUrl: str = os.getenv("BRAIN_VLM_CLOUD_URL", "")
    vlmCloudModel: str = os.getenv("BRAIN_VLM_CLOUD_MODEL", "")
    vlmOnline: bool = os.getenv("BRAIN_VLM_ONLINE", "false").lower() in ("true", "1")
    vlmDevice: str = os.getenv("BRAIN_VLM_DEVICE", DEFAULT_VLM_DEVICE)
    themePreference: str = os.getenv("VITE_THEME", "auto")
    sttProvider: str = os.getenv("BRAIN_STT_PROVIDER", "gemini_live")
    sttOnline: bool = os.getenv("BRAIN_STT_ONLINE", "false").lower() in ("true", "1")
    ttsOnline: bool = os.getenv("BRAIN_TTS_ONLINE", "true").lower() in ("true", "1")
    llmCacheEnabled: bool = True
    profiles: List[Dict[str, Any]] = []
    activeProfileId: str = ""
    robotPinHash: Optional[str] = None

    @field_validator("llmDevice", mode="before")
    @classmethod
    def _normalize_llm_device(cls, value: Any) -> str:
        return normalize_execution_device(value, default=DEFAULT_LLM_DEVICE)

    @field_validator("vlmDevice", mode="before")
    @classmethod
    def _normalize_vlm_device(cls, value: Any) -> str:
        return normalize_execution_device(value, default=DEFAULT_VLM_DEVICE)

    @field_validator("chatterboxVoiceMode", mode="before")
    @classmethod
    def _normalize_chatterbox_voice_mode(cls, value: Any) -> str:
        return normalize_chatterbox_voice_mode(value)


class AuthRequest(BaseModel):
    pin: str


class FeedbackBody(BaseModel):
    interactionId: Optional[str] = None
    rating: Optional[float] = 0
    correction: Optional[str] = ""
    context: Optional[Any] = None


class MotionBody(BaseModel):
    direction: Optional[str] = "stop"
    speed: Optional[float] = 0.0
    durationMs: Optional[int] = Field(default=0, validation_alias=AliasChoices("durationMs", "duration"))

    @field_validator("durationMs", mode="before")
    @classmethod
    def _normalize_duration_ms(cls, value: Any) -> int:
        if value is None or value == "":
            return 0
        try:
            numeric = float(value)
        except Exception:
            return 0
        if 0 < numeric <= 10:
            return int(round(numeric * 1000))
        return int(round(numeric))


class ServoBody(BaseModel):
    servoId: Optional[int] = 0
    angle: Optional[float] = 90.0


class LLMGenerateBody(BaseModel):
    provider: str
    model: str
    inputText: str
    ollamaBaseUrl: Optional[str] = None
    stream: Optional[bool] = False
    systemPrompt: Optional[str] = None
    cacheEnabled: Optional[bool] = True


class SafetyEventBody(BaseModel):
    event: str
    reason: str
    original: Optional[Any] = None
    safe: Optional[Any] = None
    ts_ms: int


def set_command_queue(command_queue: Optional[asyncio.Queue]) -> None:
    global COMMAND_QUEUE
    COMMAND_QUEUE = command_queue


def get_command_queue() -> Optional[asyncio.Queue]:
    return COMMAND_QUEUE


def set_state_manager(state_manager: Optional[RobotStateManager]) -> None:
    global STATE_MANAGER
    STATE_MANAGER = state_manager


def get_state_manager() -> Optional[RobotStateManager]:
    return STATE_MANAGER


def set_settings_path(path: str) -> None:
    global SETTINGS_PATH
    SETTINGS_PATH = path


def get_settings_path() -> str:
    return SETTINGS_PATH


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _pin_format_ok(pin: str) -> bool:
    value = str(pin or "").strip()
    return bool(re.fullmatch(rf"\d{{{PIN_MIN_LEN},{PIN_MAX_LEN}}}", value))


def _pbkdf2_hash(pin: str, *, iterations: int = 200_000, salt_bytes: bytes | None = None) -> str:
    salt = salt_bytes if salt_bytes is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _verify_pin_against_hash(pin: str, stored: str) -> bool:
    value = (stored or "").strip()
    if not value:
        return False

    if value.startswith("pbkdf2_sha256$"):
        try:
            _, iter_s, salt_hex, digest_hex = value.split("$", 3)
            iterations = int(iter_s)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except Exception:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    if re.fullmatch(r"[0-9a-fA-F]{64}", value):
        digest = hashlib.sha256(pin.encode("utf-8")).hexdigest()
        return secrets.compare_digest(value.lower(), digest.lower())

    return False


def _rate_state(ip: str) -> Dict[str, float]:
    state = rate_limit.get(ip)
    if not isinstance(state, dict):
        state = {"windowStart": time.time(), "fails": 0.0, "lockUntil": 0.0}
        rate_limit[ip] = state
    state.setdefault("windowStart", time.time())
    state.setdefault("fails", 0.0)
    state.setdefault("lockUntil", 0.0)
    return state


def _check_pin_throttle(ip: str) -> None:
    now = time.time()
    state = _rate_state(ip)
    if float(state.get("lockUntil", 0.0)) > now:
        retry_after = max(1, int(float(state["lockUntil"]) - now))
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "retryAfterSec": retry_after})
    if now - float(state.get("windowStart", now)) > PIN_FAIL_WINDOW_S:
        rate_limit.pop(ip, None)


def _record_pin_failure(ip: str) -> None:
    now = time.time()
    state = _rate_state(ip)
    if now - float(state.get("windowStart", now)) > PIN_FAIL_WINDOW_S:
        state["windowStart"] = now
        state["fails"] = 0.0
    state["fails"] = float(state.get("fails", 0.0)) + 1.0
    if state["fails"] >= float(PIN_MAX_FAILS):
        state["lockUntil"] = now + PIN_LOCKOUT_S


def _clear_pin_failures(ip: str) -> None:
    rate_limit.pop(ip, None)


async def _get_effective_pin_hash() -> Optional[str]:
    settings = await load_settings()
    if isinstance(settings.robotPinHash, str) and settings.robotPinHash.strip():
        return settings.robotPinHash.strip()
    if PIN_BOOTSTRAP_HASH:
        return PIN_BOOTSTRAP_HASH
    if PIN_BOOTSTRAP:
        return _pbkdf2_hash(PIN_BOOTSTRAP)
    return None


async def _maybe_migrate_bootstrap_pin_hash() -> None:
    if not PIN_BOOTSTRAP:
        return
    settings = await load_settings()
    if isinstance(settings.robotPinHash, str) and settings.robotPinHash.strip():
        return
    settings.robotPinHash = _pbkdf2_hash(PIN_BOOTSTRAP)
    await save_settings(settings)


async def get_current_session(
    x_robot_session: Optional[str] = Header(None, alias="x-robot-session"),
) -> str:
    session_token = get_valid_session_token(x_robot_session)
    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session_token


def get_valid_session_token(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    expiry = sessions.get(token)
    if not expiry:
        return None
    if time.time() > expiry:
        sessions.pop(token, None)
        return None
    return token


async def require_robot_auth(
    request: Request,
    x_robot_session: Optional[str] = Header(None, alias="x-robot-session"),
    x_robot_pin: Optional[str] = Header(None, alias=PIN_HEADER),
) -> str:
    session_token = get_valid_session_token(x_robot_session)
    if session_token:
        return session_token

    ip = get_client_ip(request)
    _check_pin_throttle(ip)

    effective_hash = await _get_effective_pin_hash()
    if not effective_hash:
        raise HTTPException(status_code=401, detail={"error": "pin_not_configured"})

    if x_robot_pin is None:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    candidate = x_robot_pin.strip()
    if not _pin_format_ok(candidate) or not _verify_pin_against_hash(candidate, effective_hash):
        _record_pin_failure(ip)
        raise HTTPException(status_code=401, detail={"error": "invalid_pin"})

    _clear_pin_failures(ip)
    await _maybe_migrate_bootstrap_pin_hash()
    return "pin"


async def _route_auth_dependency(
    request: Request,
    x_robot_session: Optional[str] = Header(None, alias="x-robot-session"),
    x_robot_pin: Optional[str] = Header(None, alias=PIN_HEADER),
) -> str:
    return await require_robot_auth(
        request=request,
        x_robot_session=x_robot_session,
        x_robot_pin=x_robot_pin,
    )


def get_auth_dependency():
    return _route_auth_dependency


async def require_robot_auth_dependency(
    request: Request,
    x_robot_session: Optional[str] = Header(None, alias="x-robot-session"),
    x_robot_pin: Optional[str] = Header(None, alias=PIN_HEADER),
) -> str:
    warnings.warn(
        "require_robot_auth_dependency() is deprecated; use get_auth_dependency() in route declarations.",
        DeprecationWarning,
        stacklevel=2,
    )
    return await _route_auth_dependency(
        request=request,
        x_robot_session=x_robot_session,
        x_robot_pin=x_robot_pin,
    )


def _is_sensitive_endpoint(request: Request) -> bool:
    path = request.url.path
    method = request.method.upper()

    if path.startswith("/api/admin/"):
        return True
    if path == "/api/mode" and method != "GET":
        return True
    if path.startswith("/api/motion/") and method != "GET":
        return True
    if path.startswith("/api/settings") and path not in ("/api/settings/auth", "/api/settings/check-auth", "/api/settings/logout"):
        return True
    if path == "/api/robot-settings" and method != "GET":
        return True
    if path == "/api/vision/analyze":
        return True
    if path == "/api/llm/ollama-pull":
        return True
    if path == "/api/llm/generate":
        return True
    if path == "/api/tts/chatterbox/reference-files" and method != "GET":
        return True

    return False


@app.middleware("http")
async def pin_guard_middleware(request: Request, call_next):
    if not _is_sensitive_endpoint(request):
        return await call_next(request)
    try:
        await require_robot_auth(
            request=request,
            x_robot_session=request.headers.get("x-robot-session"),
            x_robot_pin=request.headers.get(PIN_HEADER),
        )
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": "unauthorized"})

    return await call_next(request)


async def load_settings() -> RobotSettings:
    path = Path(get_settings_path()).resolve()
    if not path.exists():
        return RobotSettings()
    try:
        async with aiofiles.open(path, mode="r", encoding="utf-8") as file_obj:
            raw = json.loads(await file_obj.read())
            settings = RobotSettings(**raw)
            # Ensure environment variables are respected if JSON fields are empty
            if not settings.ollamaCloudUrl:
                settings.ollamaCloudUrl = os.getenv("BRAIN_OLLAMA_CLOUD_URL", "")
            if not settings.ollamaCloudModel:
                settings.ollamaCloudModel = os.getenv("BRAIN_OLLAMA_CLOUD_MODEL", "")
            if not settings.vlmCloudUrl:
                settings.vlmCloudUrl = os.getenv("BRAIN_VLM_CLOUD_URL", "")
            if not settings.vlmCloudModel:
                settings.vlmCloudModel = os.getenv("BRAIN_VLM_CLOUD_MODEL", "")

            if isinstance(raw, dict):
                missing_llm_device = "llmDevice" not in raw
                missing_vlm_device = "vlmDevice" not in raw
                missing_chatterbox_base_url = "chatterboxBaseUrl" not in raw
                missing_chatterbox_install_dir = "chatterboxInstallDir" not in raw
                missing_chatterbox_voice_mode = "chatterboxVoiceMode" not in raw
                missing_chatterbox_reference_audio = "chatterboxReferenceAudio" not in raw
                raw_version = raw.get("version")
                needs_version_bump = not isinstance(raw_version, int) or raw_version < CURRENT_SETTINGS_VERSION
                current_provider = str(raw.get("ttsProvider") or "").strip().lower()
                robot_language = str(raw.get("robotLanguage") or settings.robotLanguage).strip().lower()
                should_upgrade_tts_provider = (
                    needs_version_bump
                    and robot_language.startswith("ar")
                    and current_provider in {"", "pyttsx3", "gtts"}
                )
                if should_upgrade_tts_provider:
                    settings.ttsProvider = "edge"
                if (
                    missing_llm_device
                    or missing_vlm_device
                    or missing_chatterbox_base_url
                    or missing_chatterbox_install_dir
                    or missing_chatterbox_voice_mode
                    or missing_chatterbox_reference_audio
                    or needs_version_bump
                    or should_upgrade_tts_provider
                ):
                    settings.version = CURRENT_SETTINGS_VERSION
                    await save_settings(settings)
            return settings
    except Exception:
        return RobotSettings()


async def get_current_settings(session_id: str = Depends(get_current_session)) -> RobotSettings:
    return await load_settings()


async def save_settings(settings: RobotSettings) -> None:
    path = Path(get_settings_path()).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    settings.updatedAtMs = int(time.time() * 1000)
    async with aiofiles.open(path, mode="w", encoding="utf-8") as file_obj:
        await file_obj.write(settings.model_dump_json(indent=2))


async def append_motion_log(entry: dict) -> None:
    try:
        app.state.last_motion_entry = dict(entry)
        app.state.last_motion_entry_ts = int(entry.get("ts") or time.time() * 1000)
    except Exception:
        pass

    command_queue = get_command_queue()
    if command_queue is not None:
        await command_queue.put({"ts": entry.get("ts"), "kind": "motion_log", "payload": entry})
        if entry.get("type") == "motion":
            await command_queue.put(
                {
                    "kind": "motion",
                    "payload": {
                        "direction": entry.get("direction"),
                        "speed": entry.get("speed"),
                        "duration_ms": entry.get("durationMs", 0),
                    },
                }
            )
        elif entry.get("type") == "servo":
            await command_queue.put(
                {
                    "kind": "servo",
                    "payload": {
                        "servo_id": entry.get("servoId"),
                        "angle": entry.get("angle"),
                    },
                }
            )
        elif entry.get("type") == "stop":
            await command_queue.put(
                {
                    "kind": "motion",
                    "payload": {"direction": "stop", "speed": 0, "duration_ms": 0},
                }
            )
        return

    path = Path(MOTION_LOG_PATH).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, mode="a", encoding="utf-8") as file_obj:
        await file_obj.write(json.dumps(entry) + "\n")


def try_parse_action(text: str) -> dict:
    candidate = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if match:
        candidate = match.group(1)
    else:
        match = re.search(r"(\{.*\})", candidate, re.DOTALL)
        if match:
            candidate = match.group(1)
    try:
        payload = json.loads(candidate)
        if isinstance(payload, dict) and "kind" in payload:
            return payload
    except Exception:
        pass
    return {"kind": "say", "payload": {"text": candidate}}


class HearingTextBody(BaseModel):
    text: str

@app.post("/api/hearing/text")
async def post_hearing_text(body: HearingTextBody):
    queue = get_command_queue()
    if queue is not None:
        # We put a "hearing" event into the queue. 
        # The BrainRuntime handles this in its command_loop.
        await queue.put({
            "ts": int(time.time() * 1000),
            "kind": "hearing",
            "payload": {"text": body.text}
        })
        return {"success": True, "message": "Text sent to robot perception"}
    return {"success": False, "error": "Command queue not initialized"}


__all__ = [
    "app",
    "AuthRequest",
    "COMMAND_QUEUE",
    "DEBUG_LLM_PATH",
    "FeedbackBody",
    "LLMGenerateBody",
    "MAX_SAFETY_EVENTS",
    "MEMORY_DB_PATH",
    "MOTION_LOG_PATH",
    "MotionBody",
    "PIN_HEADER",
    "RobotMode",
    "RobotSettings",
    "SAFETY_EVENTS",
    "SERVER_STARTED_AT_S",
    "SESSION_DURATION",
    "ServoBody",
    "STATE_MANAGER",
    "SafetyEventBody",
    "_check_pin_throttle",
    "_clear_pin_failures",
    "_get_effective_pin_hash",
    "_maybe_migrate_bootstrap_pin_hash",
    "_pbkdf2_hash",
    "_pin_format_ok",
    "_rate_state",
    "_record_pin_failure",
    "_verify_pin_against_hash",
    "append_motion_log",
    "get_auth_dependency",
    "get_client_ip",
    "get_command_queue",
    "get_current_session",
    "get_current_settings",
    "get_settings_path",
    "get_state_manager",
    "get_valid_session_token",
    "load_settings",
    "require_robot_auth",
    "require_robot_auth_dependency",
    "save_settings",
    "set_command_queue",
    "set_settings_path",
    "set_state_manager",
    "sessions",
    "try_parse_action",
]
