import ctypes
import json
import math
import os
import platform
import socket
import subprocess
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import Depends
from pydantic import BaseModel

from .. import core
from ..runtime_info import get_runtime_info

try:
    import psutil
except ImportError:
    psutil = None

try:
    from brain.state.robot_state_manager import AudioState
except ImportError:
    AudioState = None

app = core.app
SYSTEM_HEALTH_CACHE_TTL_S = 1.75
WINDOWS_SENSOR_CACHE_TTL_S = 20.0

if psutil is not None:
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass


def _remember_override(action: str, now_ms: int) -> None:
    app.state.last_ai_override_action = action
    app.state.last_ai_override_at_ms = now_ms


def _get_override_snapshot() -> tuple[str | None, int]:
    action = getattr(app.state, "last_ai_override_action", None)
    ts_ms = int(getattr(app.state, "last_ai_override_at_ms", 0) or 0)
    return action if isinstance(action, str) and action.strip() else None, ts_ms


def _get_control_overrides() -> Dict[str, Any]:
    current = getattr(app.state, "control_overrides", None)
    if isinstance(current, dict):
        return current

    current = {}
    app.state.control_overrides = current
    return current


def _set_control_override(key: str, value: Any, now_ms: int) -> None:
    overrides = _get_control_overrides()
    overrides[key] = value
    overrides[f"{key}UpdatedAtMs"] = now_ms


def _read_state_snapshot(state_manager: Any) -> Dict[str, Any]:
    if hasattr(state_manager, "get_state_snapshot"):
        snapshot = state_manager.get_state_snapshot()
    elif hasattr(state_manager, "get_state_dict_snapshot"):
        snapshot = state_manager.get_state_dict_snapshot()
    else:
        raise AttributeError("State manager does not expose a snapshot method")

    if not isinstance(snapshot, dict):
        raise TypeError("State snapshot must be a dict")
    return snapshot


def _parse_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _normalize_percent(value: Any) -> int | None:
    numeric = _parse_number(value)
    if numeric is None:
        return None
    return max(0, min(100, int(round(numeric))))


def _normalize_optional_float(value: Any, digits: int = 1) -> float | None:
    numeric = _parse_number(value)
    if numeric is None:
        return None
    return round(numeric, digits)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        return value
    return None


def _run_powershell_json(script: str, timeout_s: float = 6.0) -> Dict[str, Any]:
    command = ["powershell", "-NoProfile", "-Command", script]
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "powershell_failed")

    payload = result.stdout.strip()
    if not payload:
        raise RuntimeError("empty_powershell_output")

    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def _filetime_to_int(filetime: Any) -> int:
    low = int(getattr(filetime, "dwLowDateTime", 0))
    high = int(getattr(filetime, "dwHighDateTime", 0))
    return (high << 32) | low


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True) if platform.system().lower() == "windows" else None
if _KERNEL32 is not None:
    _KERNEL32.GetTickCount64.restype = ctypes.c_ulonglong
    _KERNEL32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_MEMORYSTATUSEX)]
    _KERNEL32.GlobalMemoryStatusEx.restype = wintypes.BOOL
    _KERNEL32.GetSystemTimes.argtypes = [
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
        ctypes.POINTER(_FILETIME),
    ]
    _KERNEL32.GetSystemTimes.restype = wintypes.BOOL


def _read_windows_cpu_times() -> tuple[int, int, int] | None:
    if _KERNEL32 is None:
        return None

    idle = _FILETIME()
    kernel = _FILETIME()
    user = _FILETIME()
    if not _KERNEL32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None

    return (_filetime_to_int(idle), _filetime_to_int(kernel), _filetime_to_int(user))


def _calculate_windows_cpu_percent(previous: tuple[int, int, int], current: tuple[int, int, int]) -> float | None:
    idle_delta = current[0] - previous[0]
    kernel_delta = current[1] - previous[1]
    user_delta = current[2] - previous[2]
    total_delta = kernel_delta + user_delta
    if total_delta <= 0:
        return None

    busy_delta = total_delta - idle_delta
    usage = max(0.0, min(100.0, (busy_delta * 100.0) / total_delta))
    return round(usage, 1)


def _read_windows_cpu_usage_native() -> float | None:
    current = _read_windows_cpu_times()
    if current is None:
        return None

    previous = getattr(app.state, "windows_cpu_times", None)
    if not isinstance(previous, tuple) or len(previous) != 3:
        app.state.windows_cpu_times = current
        time.sleep(0.12)
        follow_up = _read_windows_cpu_times()
        if follow_up is None:
            return getattr(app.state, "windows_cpu_usage", None)
        app.state.windows_cpu_times = follow_up
        usage = _calculate_windows_cpu_percent(current, follow_up)
        if usage is not None:
            app.state.windows_cpu_usage = usage
        return usage

    app.state.windows_cpu_times = current
    usage = _calculate_windows_cpu_percent(previous, current)
    if usage is not None:
        app.state.windows_cpu_usage = usage
        return usage
    return getattr(app.state, "windows_cpu_usage", None)


def _read_windows_memory_usage_native() -> float | None:
    if _KERNEL32 is None:
        return None

    memory_status = _MEMORYSTATUSEX()
    memory_status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not _KERNEL32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
        return None

    return float(memory_status.dwMemoryLoad)


def _read_windows_boot_time_ms_native() -> int | None:
    if _KERNEL32 is None:
        return None

    try:
        tick_ms = int(_KERNEL32.GetTickCount64())
    except Exception:
        return None

    if tick_ms <= 0:
        return None
    return int(time.time() * 1000) - tick_ms


def _read_windows_sensor_probe() -> Dict[str, Any]:
    if platform.system().lower() != "windows":
        return {}

    script = r"""
$thermal = @()
$thermalSource = $null
$power = @()

try {
  $thermal = @(
    Get-CimInstance -Namespace root\LibreHardwareMonitor -Class Sensor -ErrorAction Stop |
    Where-Object { $_.SensorType -eq 'Temperature' -and ($_.Name -match 'CPU|Package|Core') } |
    Select-Object -ExpandProperty Value
  )
  if ($thermal.Count -gt 0) { $thermalSource = 'librehardwaremonitor' }
} catch {}

if ($thermal.Count -eq 0) {
  try {
    $thermal = @(
      Get-CimInstance -Namespace root\OpenHardwareMonitor -Class Sensor -ErrorAction Stop |
      Where-Object { $_.SensorType -eq 'Temperature' -and ($_.Name -match 'CPU|Package|Core') } |
      Select-Object -ExpandProperty Value
    )
    if ($thermal.Count -gt 0) { $thermalSource = 'openhardwaremonitor' }
  } catch {}
}

if ($thermal.Count -eq 0) {
  try {
    $thermal = @((Get-CimInstance -Namespace root\wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction Stop).CurrentTemperature)
    if ($thermal.Count -gt 0) { $thermalSource = 'acpi' }
  } catch {}
}

try {
  $battery = @(Get-CimInstance -Namespace root\wmi -ClassName BatteryStatus -ErrorAction Stop)
  foreach ($entry in $battery) {
    if ($entry.Discharging -and $entry.DischargeRate -gt 0) {
      $power += [double]$entry.DischargeRate / 1000
    } elseif ($entry.Charging -and $entry.ChargeRate -gt 0) {
      $power += [double]$entry.ChargeRate / 1000
    }
  }
} catch {}

[pscustomobject]@{
  thermalSamples = $thermal
  thermalSource = $thermalSource
  powerSamples = $power
} | ConvertTo-Json -Compress -Depth 4
"""

    try:
        return _run_powershell_json(script, timeout_s=2.0)
    except Exception:
        return {}


def _get_cached_windows_sensor_probe() -> Dict[str, Any]:
    now_s = time.time()
    cached = getattr(app.state, "windows_sensor_probe_cache", None)
    if isinstance(cached, dict):
        cached_at = _parse_number(cached.get("cachedAtS"))
        cached_data = cached.get("data")
        if cached_at is not None and (now_s - cached_at) <= WINDOWS_SENSOR_CACHE_TTL_S and isinstance(cached_data, dict):
            return cached_data

    stale_data = cached.get("data") if isinstance(cached, dict) else None
    data = _read_windows_sensor_probe()
    if not data and isinstance(stale_data, dict):
        return stale_data

    app.state.windows_sensor_probe_cache = {"cachedAtS": now_s, "data": data}
    return data


def _read_windows_probe() -> Dict[str, Any]:
    if platform.system().lower() != "windows":
        return {}

    sensor_probe = _get_cached_windows_sensor_probe()
    return {
        "cpuUsage": _read_windows_cpu_usage_native(),
        "ramUsage": _read_windows_memory_usage_native(),
        "bootTimeMs": _read_windows_boot_time_ms_native(),
        "thermalSamples": sensor_probe.get("thermalSamples"),
        "thermalSource": sensor_probe.get("thermalSource"),
        "powerSamples": sensor_probe.get("powerSamples"),
    }


def _read_psutil_probe() -> Dict[str, Any]:
    if psutil is None:
        return {}

    probe: Dict[str, Any] = {}

    try:
        probe["cpuUsage"] = psutil.cpu_percent(interval=None)
    except Exception:
        pass

    try:
        probe["ramUsage"] = psutil.virtual_memory().percent
    except Exception:
        pass

    try:
        probe["bootTimeMs"] = int(psutil.boot_time() * 1000)
    except Exception:
        pass

    try:
        thermal_map = psutil.sensors_temperatures(fahrenheit=False)
        thermal_samples: list[float] = []
        for entries in thermal_map.values():
            for entry in entries:
                current = _parse_number(getattr(entry, "current", None))
                if current is not None:
                    thermal_samples.append(current)
        if thermal_samples:
            probe["thermalSamples"] = thermal_samples
            probe["thermalSource"] = "psutil"
    except Exception:
        pass

    return probe


def _extract_temperature_c(samples: Any, source: str | None = None) -> float | None:
    if not isinstance(samples, list):
        return None

    values: list[float] = []
    for sample in samples:
        numeric = _parse_number(sample)
        if numeric is None:
            continue
        if numeric > 200:
            numeric -= 273.15
        if -40 <= numeric <= 150:
            values.append(numeric)

    if source == "acpi":
        values = [value for value in values if 30 <= value <= 115]

    if not values:
        return None
    return round(max(values), 1)


def _extract_power_draw_w(samples: Any) -> float | None:
    if not isinstance(samples, list):
        return None

    values = [value for value in (_parse_number(sample) for sample in samples) if value is not None and value >= 0]
    if not values:
        return None

    total = sum(values)
    if total <= 0:
        return None
    return round(total, 1)


def _calculate_uptime_s(boot_time_ms: Any) -> int | None:
    numeric = _parse_number(boot_time_ms)
    if numeric is None or numeric <= 0:
        return None

    uptime_s = int(max(0, (time.time() * 1000 - numeric) / 1000))
    return uptime_s


def _measure_tcp_ping_ms(target_url: str | None) -> float | None:
    if not target_url:
        return None

    try:
        parsed = urlparse(target_url)
    except Exception:
        return None

    host = parsed.hostname
    if not host:
        return None

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=0.35):
            pass
    except OSError:
        return None

    return round((time.perf_counter() - started) * 1000, 1)


def _build_service_ping_targets(settings: core.RobotSettings) -> list[str]:
    raw_targets = [
        os.getenv("ROBOT_SERVICE_PING_URL", "").strip(),
        str(settings.ollamaBaseUrl or "").strip(),
        str(settings.vlmBaseUrl or "").strip(),
    ]

    backend_port = str(os.getenv("ROBOT_WEB_UI_PORT") or os.getenv("PORT") or "8000").strip()
    if backend_port.isdigit():
        raw_targets.extend(
            [
                f"http://127.0.0.1:{backend_port}/api/health",
                f"http://localhost:{backend_port}/api/health",
            ]
        )

    seen: set[str] = set()
    targets: list[str] = []
    for target in raw_targets:
        if not target or target in seen:
            continue
        seen.add(target)
        targets.append(target)
    return targets


def _measure_first_reachable_ping_ms(targets: list[str]) -> float | None:
    for target in targets:
        ping = _measure_tcp_ping_ms(target)
        if ping is not None:
            return ping
    return None


def _read_last_motion_entry() -> Dict[str, Any] | None:
    cached = getattr(app.state, "last_motion_entry", None)
    if isinstance(cached, dict):
        return cached

    path = Path(core.MOTION_LOG_PATH).resolve()
    if not path.exists():
        return None

    try:
        size = path.stat().st_size
        with path.open("rb") as file_obj:
            file_obj.seek(max(size - 4096, 0))
            lines = file_obj.read().decode("utf-8", errors="ignore").splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _stringify_state_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = value.value
    text = str(value).strip()
    return text or None


def _voice_module_name(settings: core.RobotSettings) -> str | None:
    provider = str(settings.ttsProvider or "").strip()
    gender = str(settings.ttsVoiceGender or "").strip()
    parts = [part for part in (provider, gender) if part]
    return " / ".join(parts) if parts else None


def _derive_current_task(
    now_ms: int,
    override_action: str | None,
    override_ts_ms: int,
    snapshot: Dict[str, Any] | None,
    queue_size: int,
    motion_entry: Dict[str, Any] | None,
) -> str:
    if override_action and (now_ms - override_ts_ms) < 30_000:
        return override_action.upper()

    motion_ts_ms = int((motion_entry or {}).get("ts") or 0)
    if motion_entry and motion_ts_ms > 0 and (now_ms - motion_ts_ms) < 30_000:
        motion_type = str(motion_entry.get("type") or "").lower()
        if motion_type == "motion":
            direction = str(motion_entry.get("direction") or "move").upper()
            return f"MOTION_{direction}"
        if motion_type == "stop":
            return "MOTION_STOP"
        if motion_type == "servo":
            servo_id = motion_entry.get("servoId")
            angle = motion_entry.get("angle")
            return f"SERVO_{servo_id}_{angle}"

    audio_state = _stringify_state_value((snapshot or {}).get("audio_state"))
    if audio_state == "PROCESSING":
        return "VOICE_PROCESSING"
    if audio_state == "ACTIVE":
        return "VOICE_ACTIVE"

    if queue_size > 0:
        return "QUEUE_ACTIVE"

    mode = _stringify_state_value((snapshot or {}).get("mode"))
    if mode:
        return f"MODE_{mode}"

    return "IDLE"


async def _collect_system_health() -> Dict[str, Any]:
    settings = await core.load_settings()
    psutil_probe = _read_psutil_probe()
    windows_probe = _read_windows_probe()
    thermal_samples = _coalesce(psutil_probe.get("thermalSamples"), windows_probe.get("thermalSamples"))
    thermal_source = _coalesce(psutil_probe.get("thermalSource"), windows_probe.get("thermalSource"))
    power_samples = _coalesce(windows_probe.get("powerSamples"))

    return {
        "cpuUsage": _normalize_percent(_coalesce(psutil_probe.get("cpuUsage"), windows_probe.get("cpuUsage"))),
        "cpuTemp": _extract_temperature_c(thermal_samples, thermal_source),
        "ramUsage": _normalize_percent(_coalesce(psutil_probe.get("ramUsage"), windows_probe.get("ramUsage"))),
        "uptime": _calculate_uptime_s(_coalesce(psutil_probe.get("bootTimeMs"), windows_probe.get("bootTimeMs"))),
        "powerDraw": _extract_power_draw_w(power_samples),
        "ping": _measure_first_reachable_ping_ms(_build_service_ping_targets(settings)),
    }


async def _get_cached_system_health() -> Dict[str, Any]:
    now_s = time.time()
    cached = getattr(app.state, "system_health_cache", None)
    if isinstance(cached, dict):
        cached_at = _parse_number(cached.get("cachedAtS"))
        cached_data = cached.get("data")
        if cached_at is not None and (now_s - cached_at) <= SYSTEM_HEALTH_CACHE_TTL_S and isinstance(cached_data, dict):
            return cached_data

    data = await _collect_system_health()
    app.state.system_health_cache = {"cachedAtS": now_s, "data": data}
    return data


@app.get("/api/status")
async def get_robot_status():
    now_ms = int(time.time() * 1000)
    state_manager = core.get_state_manager()
    if state_manager:
        snapshot = _read_state_snapshot(state_manager)
        last_ack = snapshot.get("last_heartbeat_ack_ms", 0)
        heartbeat_healthy = (now_ms - last_ack) < 2000 if last_ack > 0 else False
        return {
            "success": True,
            "state": snapshot,
            "heartbeat_healthy": heartbeat_healthy,
            "timestamp_ms": now_ms,
        }

    return {
        "success": False,
        "error": "State manager not initialized",
        "state": {},
        "heartbeat_healthy": False,
        "timestamp_ms": now_ms,
    }


@app.get("/api/health/system")
async def get_system_health():
    metrics = await _get_cached_system_health()
    runtime_info = await get_runtime_info()
    return {
        "success": True,
        "freshAtMs": int(time.time() * 1000),
        "degraded": bool(runtime_info.get("degraded")),
        "errorCode": runtime_info.get("errorCode"),
        "message": "System metrics captured" if not runtime_info.get("degraded") else runtime_info.get("message"),
        "host": runtime_info.get("host"),
        **metrics,
    }


@app.get("/api/ai/state")
async def get_ai_state():
    now_ms = int(time.time() * 1000)
    settings = await core.load_settings()
    override_action, override_ts_ms = _get_override_snapshot()
    runtime_info = await get_runtime_info()

    state_manager = core.get_state_manager()
    snapshot = _read_state_snapshot(state_manager) if state_manager else None

    queue_size = 0
    command_queue = core.get_command_queue()
    if command_queue is not None:
        try:
            queue_size = int(command_queue.qsize())
        except Exception:
            queue_size = 0

    overrides = _get_control_overrides()
    manual_audio_state = _stringify_state_value(overrides.get("audioState"))
    motion_entry = _read_last_motion_entry()
    audio_state = _stringify_state_value((snapshot or {}).get("audio_state")) or manual_audio_state
    is_processing = audio_state == "PROCESSING" or queue_size > 0
    degraded = state_manager is None
    message = "Standalone host mode: state manager unavailable" if degraded else "AI state snapshot captured"

    tts_status = {}
    try:
        status_path = Path(core.MOTION_LOG_PATH).resolve().parent / "tts_status.json"
        if status_path.exists():
            with status_path.open("r") as f:
                tts_status = json.load(f)
    except Exception:
        pass

    return {
        "success": True,
        "freshAtMs": now_ms,
        "degraded": degraded,
        "errorCode": "state_manager_unavailable" if degraded else runtime_info.get("errorCode"),
        "message": message,
        "llmDevice": core.normalize_execution_device(settings.llmDevice, default=core.DEFAULT_LLM_DEVICE),
        "visionModel": _stringify_state_value(settings.vlmModel),
        "visionDevice": core.normalize_execution_device(settings.vlmDevice, default=core.DEFAULT_VLM_DEVICE),
        "voiceModel": _voice_module_name(settings),
        "isProcessing": is_processing,
        "currentTask": _derive_current_task(now_ms, override_action, override_ts_ms, snapshot, queue_size, motion_entry),
        "mode": _stringify_state_value((snapshot or {}).get("mode")),
        "audioState": audio_state,
        "visionLayer": _stringify_state_value((snapshot or {}).get("vision_layer")),
        "speedLimit": _normalize_optional_float((snapshot or {}).get("speed_limit"), 2),
        "coolingMode": _stringify_state_value(overrides.get("coolingMode")),
        "servoTorque": _stringify_state_value(overrides.get("servoTorque")),
        "ttsStatus": tts_status,
    }


class ModeBody(BaseModel):
    mode: str


class AiOverrideBody(BaseModel):
    action: str


@app.get("/api/mode")
async def get_robot_mode():
    state_manager = core.get_state_manager()
    if state_manager:
        return {"success": True, "mode": state_manager.get_mode().value}
    return {"success": False, "error": "State manager not initialized"}


@app.post("/api/mode")
async def set_robot_mode(body: ModeBody, _auth: str = Depends(core.get_auth_dependency())):
    state_manager = core.get_state_manager()
    if not state_manager:
        return {"success": False, "error": "State manager not initialized"}

    try:
        mode_str = body.mode.upper()
        if hasattr(core.RobotMode, mode_str):
            mode_enum = getattr(core.RobotMode, mode_str)
        else:
            return {"success": False, "error": f"Invalid mode: {body.mode}"}
        return {"success": state_manager.set_mode(mode_enum)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.api_route("/api/ai/override", methods=["POST", "PUT"])
async def ai_override(body: AiOverrideBody, _auth: str = Depends(core.get_auth_dependency())):
    action = str(body.action or "").strip().lower()
    if not action:
        return {"success": False, "error": "invalid_action"}

    now_ms = int(time.time() * 1000)
    _remember_override(action, now_ms)

    state_manager = core.get_state_manager()
    applied_mode = None

    if action == "emergency_halt":
        await core.append_motion_log({"ts": now_ms, "type": "stop"})
        if state_manager and hasattr(core.RobotMode, "EMERGENCY"):
            state_manager.set_mode(getattr(core.RobotMode, "EMERGENCY"))
            applied_mode = "EMERGENCY"
    elif action == "loop_pause":
        if state_manager and hasattr(core.RobotMode, "IDLE"):
            state_manager.set_mode(getattr(core.RobotMode, "IDLE"))
            applied_mode = "IDLE"
    elif action == "loop_resume":
        if state_manager and hasattr(core.RobotMode, "NAV"):
            state_manager.set_mode(getattr(core.RobotMode, "NAV"))
            applied_mode = "NAV"
    elif action == "fans_max":
        _set_control_override("coolingMode", "MAX", now_ms)
    elif action == "torque_release":
        _set_control_override("servoTorque", "RELEASED", now_ms)

    command_queue = core.get_command_queue()
    queued = False
    if command_queue is not None:
        await command_queue.put({"kind": "ai_override", "payload": {"action": action, "ts_ms": now_ms}})
        queued = True

    return {"success": True, "action": action, "queued": queued, "mode": applied_mode}


@app.api_route("/api/ai/wake", methods=["POST", "PUT"])
async def ai_wake(_auth: str = Depends(core.get_auth_dependency())):
    now_ms = int(time.time() * 1000)
    _remember_override("wake_up_ai", now_ms)
    _set_control_override("audioState", "ACTIVE", now_ms)

    state_manager = core.get_state_manager()
    applied_audio_state = "ACTIVE"
    if state_manager and AudioState is not None and hasattr(AudioState, "ACTIVE") and hasattr(state_manager, "set_audio_state"):
        try:
            state_manager.set_audio_state(getattr(AudioState, "ACTIVE"))
        except Exception:
            pass

    return {"success": True, "audioState": applied_audio_state}

@app.get("/api/debug_snapshot")
async def get_debug_snapshot():
    snapshot = core.get_runtime_debug_snapshot()
    if snapshot:
        return {"success": True, "snapshot": snapshot}
    return {"success": False, "error": "No debug snapshot available yet"}

class DebugVoiceBody(BaseModel):
    voiceGender: str

@app.post("/api/debug/voice")
async def update_debug_voice(body: DebugVoiceBody):
    settings = await core.load_settings()
    settings.ttsVoiceGender = body.voiceGender
    await core.save_settings(settings)
    command_queue = core.get_command_queue()
    if command_queue is not None:
        await command_queue.put({"kind": "reload_settings", "payload": {}})
    return {"success": True}

@app.get("/api/debate/state")
async def get_debate_state():
    try:
        # Use project root data dir (matches debate_engine.py's DEBATE_LOGS_PATH)
        from ..runtime_paths import get_app_root
        project_root = get_app_root(__file__, depth=5)
        log_path = project_root / "data" / "debate_logs.json"
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return {"success": True, "is_debating": data.get("is_debating", False), "logs": data.get("logs", [])}
    except Exception:
        pass
    return {"success": True, "is_debating": False, "logs": []}
