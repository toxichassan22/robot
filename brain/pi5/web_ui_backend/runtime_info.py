from __future__ import annotations

import importlib.util
import os
import platform
import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

from . import core
from brain.speech.chatterbox_client import probe_chatterbox


RUNTIME_INFO_TTL_S = 5.0


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _safe_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return platform.node() or "unknown-host"


def _safe_platform_name() -> str:
    parts = [platform.system(), platform.release()]
    text = " ".join(part for part in parts if part).strip()
    return text or sys.platform


def _resolve_port() -> int:
    raw = str(os.getenv("ROBOT_WEB_UI_PORT") or os.getenv("ROBOT_PORT") or os.getenv("PORT") or "8000").strip()
    if raw.isdigit():
        return int(raw)
    return 8000


def _resolve_host_mode() -> tuple[str, str]:
    raw = str(os.getenv("ROBOT_HOST_MODE", "auto")).strip().lower()
    if raw in {"laptop", "mini-pc"}:
        return raw, "env"

    hostname = _safe_hostname().lower()
    if any(token in hostname for token in ("mini", "nuc", "pi", "robotbox")):
        return "mini-pc", "auto"
    return "laptop", "auto"


def _detect_lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass

    try:
        candidates = socket.gethostbyname_ex(_safe_hostname())[2]
    except Exception:
        candidates = []

    for candidate in candidates:
        if candidate and not candidate.startswith("127.") and not candidate.startswith("169.254."):
            return candidate
    return None


def _build_host_payload() -> Dict[str, Any]:
    host_mode, host_mode_source = _resolve_host_mode()
    port = _resolve_port()
    lan_ip = _detect_lan_ip()
    return {
        "hostname": _safe_hostname(),
        "platform": _safe_platform_name(),
        "pythonVersion": sys.version.split()[0],
        "mode": host_mode,
        "modeSource": host_mode_source,
        "port": port,
        "localUrl": f"http://127.0.0.1:{port}",
        "lanIp": lan_ip,
        "lanUrl": f"http://{lan_ip}:{port}" if lan_ip else None,
    }


def _motion_capability() -> Dict[str, Any]:
    command_queue = core.get_command_queue()
    if command_queue is not None:
        return {
            "configured": True,
            "supported": True,
            "ready": True,
            "degraded": False,
            "message": "Command queue attached",
        }

    path = Path(core.MOTION_LOG_PATH).resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "configured": True,
            "supported": True,
            "ready": True,
            "degraded": False,
            "message": "Fallback motion log enabled",
        }
    except Exception as exc:
        return {
            "configured": True,
            "supported": False,
            "ready": False,
            "degraded": True,
            "message": f"Motion backend unavailable: {exc}",
        }


def _camera_capability() -> Dict[str, Any]:
    supported = _module_available("cv2")
    return {
        "configured": True,
        "supported": supported,
        "ready": supported,
        "degraded": not supported,
        "message": "OpenCV available" if supported else "OpenCV is not installed on host",
    }


async def _tts_capability(settings: core.RobotSettings) -> Dict[str, Any]:
    provider = str(settings.ttsProvider or "edge").strip().lower()
    if provider == "chatterbox":
        payload = await probe_chatterbox(settings.chatterboxBaseUrl)
        payload["provider"] = provider
        return payload
    if provider == "gemini":
        configured = bool(os.getenv("BRAIN_GEMINI_API_KEY", "").strip())
        return {
            "configured": configured,
            "provider": provider,
            "supported": True,
            "ready": configured,
            "degraded": not configured,
            "message": "Gemini Live audio configured" if configured else "BRAIN_GEMINI_API_KEY is missing",
        }

    provider_modules = {
        "edge": ("edge_tts",),
        "pyttsx3": ("pyttsx3",),
        "gtts": ("gtts",),
        "coqui": ("TTS", "coqui_tts"),
    }
    supported = any(_module_available(module_name) for module_name in provider_modules.get(provider, (provider,)))
    return {
        "configured": True,
        "provider": provider,
        "supported": supported,
        "ready": supported,
        "degraded": not supported,
        "message": f"{provider} available" if supported else f"{provider} dependencies are missing",
    }


def _stt_capability() -> Dict[str, Any]:
    return {
        "configured": True,
        "supported": True,
        "ready": True,
        "degraded": False,
        "mode": "gemini-live",
        "message": "Speech recognition is handled by Gemini Live audio",
    }


async def _probe_remote_tags(base_url: str) -> Dict[str, Any]:
    target = str(base_url or "").strip()
    if not target:
        return {
            "configured": False,
            "supported": False,
            "ready": False,
            "reachable": False,
            "degraded": True,
            "message": "Service URL is empty",
        }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{target.rstrip('/')}/api/tags", timeout=10.0)
        if response.status_code >= 400:
            return {
                "configured": True,
                "supported": True,
                "ready": False,
                "reachable": False,
                "degraded": True,
                "message": f"Service responded with HTTP {response.status_code}",
            }
        return {
            "configured": True,
            "supported": True,
            "ready": True,
            "reachable": True,
            "degraded": False,
            "message": "Service reachable",
        }
    except Exception as exc:
        return {
            "configured": True,
            "supported": True,
            "ready": False,
            "reachable": False,
            "degraded": True,
            "message": f"Service unreachable: {exc}",
        }


def _summarize_runtime_state(services: Dict[str, Dict[str, Any]]) -> tuple[bool, bool, str | None, str]:
    degraded_names = [name for name, payload in services.items() if bool(payload.get("degraded"))]
    required_ready = all(
        bool(services[name].get("ready"))
        for name in ("motion",)
        if name in services
    )
    ready = required_ready and not degraded_names
    degraded = bool(degraded_names)
    if ready:
        return True, False, None, "Host services ready"
    if degraded:
        return False, True, "service_degraded", f"Degraded services: {', '.join(degraded_names)}"
    return False, False, None, "Host running"


async def _build_runtime_info() -> Dict[str, Any]:
    settings = await core.load_settings()
    services = {
        "llm": await _probe_remote_tags(settings.ollamaBaseUrl),
        "vlm": await _probe_remote_tags(settings.vlmBaseUrl),
        "cloud_llm": await _probe_remote_tags(settings.ollamaCloudUrl),
        "cloud_vlm": await _probe_remote_tags(settings.vlmCloudUrl),
        "tts": await _tts_capability(settings),
        "stt": _stt_capability(),
        "camera": _camera_capability(),
        "motion": _motion_capability(),
    }
    ready, degraded, error_code, message = _summarize_runtime_state(services)
    fresh_at_ms = int(time.time() * 1000)
    return {
        "freshAtMs": fresh_at_ms,
        "ready": ready,
        "degraded": degraded,
        "errorCode": error_code,
        "message": message,
        "host": _build_host_payload(),
        "services": services,
    }


async def get_runtime_info(force: bool = False) -> Dict[str, Any]:
    now_s = time.time()
    cached = getattr(core.app.state, "runtime_info_cache", None)
    if not force and isinstance(cached, dict):
        cached_at_s = cached.get("cachedAtS")
        payload = cached.get("payload")
        if isinstance(cached_at_s, (int, float)) and isinstance(payload, dict) and (now_s - float(cached_at_s)) <= RUNTIME_INFO_TTL_S:
            return payload

    payload = await _build_runtime_info()
    core.app.state.runtime_info_cache = {"cachedAtS": now_s, "payload": payload}
    return payload


def get_runtime_service_payload(runtime_info: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    services = runtime_info.get("services")
    return services if isinstance(services, dict) else {}
