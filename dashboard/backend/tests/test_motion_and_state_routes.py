import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from pi_5.web_ui_backend import core
from pi_5.web_ui_backend.main import app
from pi_5.web_ui_backend.routers import state


client = TestClient(app)


def _mock_auth_bypass():
    return patch("pi_5.web_ui_backend.core.require_robot_auth", return_value="test")


def test_motion_move_accepts_duration_alias_and_normalizes_to_ms():
    append_motion_log = AsyncMock()

    with _mock_auth_bypass(), patch("pi_5.web_ui_backend.core.append_motion_log", append_motion_log):
        response = client.post(
            "/api/motion/move",
            json={"direction": "forward", "speed": 50, "duration": 1.2},
            headers={"x-robot-pin": "1234"},
        )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    append_motion_log.assert_awaited_once()
    payload = append_motion_log.await_args.args[0]
    assert payload["direction"] == "forward"
    assert payload["speed"] == 50
    assert payload["durationMs"] == 1200


def test_motion_halt_alias_routes_to_stop_behavior():
    append_motion_log = AsyncMock()

    with _mock_auth_bypass(), patch("pi_5.web_ui_backend.core.append_motion_log", append_motion_log):
        response = client.post("/api/motion/halt", json={}, headers={"x-robot-pin": "1234"})

    assert response.status_code == 200
    assert response.json() == {"success": True}
    append_motion_log.assert_awaited_once()
    payload = append_motion_log.await_args.args[0]
    assert payload["type"] == "stop"


def test_motion_calibrate_queues_servo_home_command():
    append_motion_log = AsyncMock()

    with _mock_auth_bypass(), patch("pi_5.web_ui_backend.core.append_motion_log", append_motion_log):
        response = client.post("/api/motion/calibrate", json={}, headers={"x-robot-pin": "1234"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["servoId"] == 0
    assert data["angle"] == 90.0
    append_motion_log.assert_awaited_once()
    payload = append_motion_log.await_args.args[0]
    assert payload["type"] == "servo"
    assert payload["servoId"] == 0
    assert payload["angle"] == 90.0


def test_ai_override_emergency_halt_records_stop_and_sets_mode():
    append_motion_log = AsyncMock()
    state_manager = MagicMock()

    with _mock_auth_bypass(), patch("pi_5.web_ui_backend.core.append_motion_log", append_motion_log), patch(
        "pi_5.web_ui_backend.core.get_state_manager", return_value=state_manager
    ):
        response = client.post(
            "/api/ai/override",
            json={"action": "emergency_halt"},
            headers={"x-robot-pin": "1234"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["action"] == "emergency_halt"
    assert data["mode"] == "EMERGENCY"
    append_motion_log.assert_awaited_once()
    state_manager.set_mode.assert_called_once()


def test_ai_wake_sets_audio_state_when_state_manager_available():
    state_manager = MagicMock()

    with _mock_auth_bypass(), patch("pi_5.web_ui_backend.core.get_state_manager", return_value=state_manager):
        response = client.post("/api/ai/wake", json={}, headers={"x-robot-pin": "1234"})

    assert response.status_code == 200
    assert response.json() == {"success": True, "audioState": "ACTIVE"}
    state_manager.set_audio_state.assert_called_once()


def test_ai_state_uses_real_settings_and_runtime_snapshot():
    settings = core.RobotSettings(vlmModel="moondream", ttsProvider="pyttsx3", ttsVoiceGender="female")
    state_manager = MagicMock()
    state_manager.get_state_snapshot.return_value = {
        "mode": "NAV",
        "audio_state": "PROCESSING",
        "vision_layer": 3,
        "speed_limit": 0.4,
    }
    queue = MagicMock()
    queue.qsize.return_value = 2

    with patch("pi_5.web_ui_backend.core.load_settings", AsyncMock(return_value=settings)), patch(
        "pi_5.web_ui_backend.core.get_state_manager", return_value=state_manager
    ), patch("pi_5.web_ui_backend.core.get_command_queue", return_value=queue), patch(
        "pi_5.web_ui_backend.routers.state._get_override_snapshot",
        return_value=(None, 0),
    ), patch(
        "pi_5.web_ui_backend.routers.state._read_last_motion_entry",
        return_value={"ts": 0, "type": "stop"},
    ):
        response = client.get("/api/ai/state")

    assert response.status_code == 200
    data = response.json()
    assert data["visionModel"] == "moondream"
    assert data["voiceModel"] == "pyttsx3 / female"
    assert data["isProcessing"] is True
    assert data["currentTask"] == "VOICE_PROCESSING"
    assert data["mode"] == "NAV"
    assert data["audioState"] == "PROCESSING"
    assert data["visionLayer"] == "3"
    assert data["speedLimit"] == 0.4


def test_measure_first_reachable_ping_ms_uses_first_live_target():
    with patch(
        "pi_5.web_ui_backend.routers.state._measure_tcp_ping_ms",
        side_effect=[None, 7.4, 12.1],
    ) as measure_ping:
        result = state._measure_first_reachable_ping_ms(["http://offline", "http://live", "http://unused"])

    assert result == 7.4
    assert [call.args[0] for call in measure_ping.call_args_list] == ["http://offline", "http://live"]


def test_collect_system_health_prefers_host_probe_and_backend_ping_fallback():
    settings = core.RobotSettings(
        ollamaBaseUrl="http://127.0.0.1:11434",
        vlmBaseUrl="http://127.0.0.1:11435",
    )

    with patch("pi_5.web_ui_backend.core.load_settings", AsyncMock(return_value=settings)), patch(
        "pi_5.web_ui_backend.routers.state._read_psutil_probe",
        return_value={
            "cpuUsage": 14.4,
            "ramUsage": 38.2,
            "bootTimeMs": 1_500_000,
        },
    ), patch(
        "pi_5.web_ui_backend.routers.state._read_windows_probe",
        return_value={
            "cpuUsage": 61.0,
            "ramUsage": 72.0,
            "bootTimeMs": 900_000,
            "thermalSamples": [301.15],
            "powerSamples": [2.8],
        },
    ), patch(
        "pi_5.web_ui_backend.routers.state._build_service_ping_targets",
        return_value=["http://offline", "http://backend"],
    ), patch(
        "pi_5.web_ui_backend.routers.state._measure_first_reachable_ping_ms",
        return_value=5.6,
    ), patch(
        "pi_5.web_ui_backend.routers.state.time.time",
        return_value=2_000.0,
    ):
        data = asyncio.run(state._collect_system_health())

    assert data == {
        "cpuUsage": 14,
        "cpuTemp": 28.0,
        "ramUsage": 38,
        "uptime": 500,
        "powerDraw": 2.8,
        "ping": 5.6,
    }


def test_safety_events_limit_returns_latest_subset():
    with patch(
        "pi_5.web_ui_backend.core.SAFETY_EVENTS",
        [
            {"event": "a", "reason": "x", "ts_ms": 1},
            {"event": "b", "reason": "y", "ts_ms": 2},
            {"event": "c", "reason": "z", "ts_ms": 3},
        ],
    ):
        response = client.get("/api/safety-events?limit=2")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert [event["event"] for event in data["events"]] == ["b", "c"]
