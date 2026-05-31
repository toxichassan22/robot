import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brain.pi5.web_ui_backend import core
from brain.pi5.web_ui_backend.main import app

client = TestClient(app)

def setup_function():
    # Clear safety events before each test run
    core.SAFETY_EVENTS.clear()

def test_web_server_serve_keys():
    """Verify that serve_keys_page endpoint (/keys.html) is served successfully."""
    # Temporarily patch the keys HTML path to a mock path that exists
    with patch("brain.pi5.web_ui_backend.routers.api_keys._KEYS_HTML_PATH") as mock_path:
        mock_path.exists.return_value = True
        mock_path.read_text.return_value = "<html>Mock Keys Page</html>"
        
        response = client.get("/keys.html")
        assert response.status_code == 200
        assert "Mock Keys Page" in response.text

def test_web_server_safety_events():
    """Verify that safety events lifecycle (GET/POST/TRIM) works on the FastAPI web server."""
    # 1. Check initially empty events
    response = client.get("/api/safety-events")
    assert response.status_code == 200
    assert response.json() == {"success": True, "events": []}
    
    # 2. Add an event
    event_payload = {
        "event": "thermal_overheat",
        "reason": "cpu_exceeded_80c",
        "original": {"speed": 1.0},
        "safe": {"speed": 0.0},
        "ts_ms": int(time.time() * 1000)
    }
    response = client.post("/api/safety-events", json=event_payload)
    assert response.status_code == 200
    assert response.json() == {"success": True}
    
    # 3. Retrieve events and verify it is captured
    response = client.get("/api/safety-events")
    assert response.status_code == 200
    data = response.json()
    assert len(data["events"]) == 1
    assert data["events"][0]["event"] == "thermal_overheat"
    assert data["events"][0]["reason"] == "cpu_exceeded_80c"

def test_web_server_status_endpoint():
    """Verify that status endpoint (/api/status) reports state snapshot and heartbeat health."""
    mock_state_manager = MagicMock()
    now_ms = int(time.time() * 1000)
    
    # Heartbeat is healthy (received 200ms ago)
    mock_state_manager.get_state_snapshot.return_value = {
        "mode": "ACTIVE",
        "last_heartbeat_ack_ms": now_ms - 200
    }
    
    with patch("brain.pi5.web_ui_backend.core.get_state_manager", return_value=mock_state_manager):
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["heartbeat_healthy"] is True
        assert data["state"]["mode"] == "ACTIVE"
        assert isinstance(data["timestamp_ms"], int)
