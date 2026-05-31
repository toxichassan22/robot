
import pytest
import time
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from brain.pi5.web_ui_backend import core
from brain.pi5.web_ui_backend.main import app

client = TestClient(app)

def setup_function():
    # Clear safety events before each test
    core.SAFETY_EVENTS.clear()

def test_safety_events_lifecycle():
    # 1. Verify empty start
    response = client.get("/api/safety-events")
    assert response.status_code == 200
    assert response.json() == {"success": True, "events": []}

    # 2. Post an event
    event_payload = {
        "event": "collision_warning",
        "reason": "lidar_proximity",
        "original": {"speed": 1.0},
        "safe": {"speed": 0.0},
        "ts_ms": int(time.time() * 1000)
    }
    
    response = client.post("/api/safety-events", json=event_payload)
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # 3. Verify event is present
    response = client.get("/api/safety-events")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["events"]) == 1
    assert data["events"][0]["event"] == "collision_warning"

def test_safety_events_trimming():
    # Add 55 events
    for i in range(55):
        event_payload = {
            "event": f"event_{i}",
            "reason": "test",
            "ts_ms": int(time.time() * 1000)
        }
        client.post("/api/safety-events", json=event_payload)

    # Verify only 50 exist and we have the latest ones
    response = client.get("/api/safety-events")
    data = response.json()
    assert len(data["events"]) == 50
    # The first one should be the 6th event (index 5) if we popped from 0
    # 0..54 inserted. 5 popped. 5,6...54 remain.
    # checking the last one is safer to verify order
    assert data["events"][-1]["event"] == "event_54"

def test_status_endpoint():
    # Mock STATE_MANAGER
    mock_state_manager = MagicMock()
    
    # Snapshot relative logic
    now_ms = int(time.time() * 1000)
    # Case 1: Healthy heartbeat (ack 100ms ago)
    mock_state_manager.get_state_snapshot.return_value = {
        "mode": "IDLE",
        "last_heartbeat_ack_ms": now_ms - 100
    }

    with patch("brain.pi5.web_ui_backend.core.get_state_manager", return_value=mock_state_manager):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["heartbeat_healthy"] is True
        assert isinstance(data["timestamp_ms"], int)
        assert data["state"]["mode"] == "IDLE"

    # Case 2: Unhealthy heartbeat (ack 3000ms ago)
    mock_state_manager.get_state_snapshot.return_value = {
        "mode": "IDLE",
        "last_heartbeat_ack_ms": now_ms - 3000
    }
    
    with patch("brain.pi5.web_ui_backend.core.get_state_manager", return_value=mock_state_manager):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["heartbeat_healthy"] is False
