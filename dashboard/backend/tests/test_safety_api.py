from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from pi_5.web_ui_backend import core
from pi_5.web_ui_backend.main import app

client = TestClient(app)

def setup_function():
    core.SAFETY_EVENTS.clear()

def test_post_safety_event():
    """Test POST /api/safety-events appends event and trims list."""
    # Test valid post
    payload = {
        "event": "obstacle_detected",
        "reason": "proximity_sensor",
        "original": {"dist": 10},
        "safe": {"dist": 20},
        "ts_ms": 1234567890
    }
    response = client.post("/api/safety-events", json=payload)
    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert len(core.SAFETY_EVENTS) == 1
    assert core.SAFETY_EVENTS[0]["event"] == "obstacle_detected"

    # Test trimming
    # Fill up to max + 1
    for i in range(core.MAX_SAFETY_EVENTS + 5):
        client.post("/api/safety-events", json={
            "event": f"event_{i}",
            "reason": "test",
            "ts_ms": 1000 + i
        })
    
    assert len(core.SAFETY_EVENTS) == core.MAX_SAFETY_EVENTS
    # Should have trimmed the oldest (event_0, event_1, etc dropped)
    # The last one added should be event_(MAX+4)
    assert core.SAFETY_EVENTS[-1]["event"] == f"event_{core.MAX_SAFETY_EVENTS + 4}"

def test_get_safety_events():
    """Test GET /api/safety-events returns correct structure."""
    # Pre-populate
    event = {
        "event": "test_event",
        "reason": "test_reason",
        "ts_ms": 12345
    }
    core.SAFETY_EVENTS.append(event)
    
    response = client.get("/api/safety-events")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["events"]) == 1
    assert data["events"][0]["event"] == "test_event"

@patch("pi_5.web_ui_backend.core.get_state_manager")
def test_get_status(mock_get_state_manager):
    """Test /api/status with mocked STATE_MANAGER."""
    import time
    mock_state_manager = MagicMock()
    mock_get_state_manager.return_value = mock_state_manager
    
    # Mocking get_state_snapshot
    # Case 1: Healthy heartbeat
    now_ms = int(time.time() * 1000)
    mock_state_manager.get_state_snapshot.return_value = {
        "last_heartbeat_ack_ms": now_ms - 500, # 500ms ago (within 2000ms)
        "some_other_state": "foo"
    }
    
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["heartbeat_healthy"] is True
    assert "timestamp_ms" in data
    assert isinstance(data["timestamp_ms"], int)
    assert data["state"]["some_other_state"] == "foo"
    
    # Case 2: Unhealthy heartbeat (stale)
    mock_state_manager.get_state_snapshot.return_value = {
        "last_heartbeat_ack_ms": now_ms - 3000, # 3000ms ago (> 2000ms)
    }
    
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["heartbeat_healthy"] is False

    # Case 3: No heartbeat ever
    mock_state_manager.get_state_snapshot.return_value = {
        "last_heartbeat_ack_ms": 0
    }
    response = client.get("/api/status")
    data = response.json()
    assert data["heartbeat_healthy"] is False

def test_status_no_manager():
    """Test /api/status when STATE_MANAGER is None."""
    with patch("pi_5.web_ui_backend.core.get_state_manager", return_value=None):
        response = client.get("/api/status")
        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "error" in response.json()
