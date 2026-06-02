import sys
import time
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brain.activity.types import ChestActivityEvent
from brain.activity.bus import get_activity_bus, ActivityBus
from brain.pi5.web_ui_backend.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_activity_bus_publishing():
    """Verify that ActivityBus handles publishing, buffer max size, and ordering correctly."""
    # Create isolated bus
    bus = ActivityBus(max_history=3)
    
    # Check initial snapshot
    snapshot = await bus.snapshot()
    assert len(snapshot) == 0

    # Publish events
    e1 = ChestActivityEvent(id="1", tsMs=1000, phase="listening", source="runtime", title="Event 1")
    e2 = ChestActivityEvent(id="2", tsMs=2000, phase="thinking", source="runtime", title="Event 2")
    e3 = ChestActivityEvent(id="3", tsMs=3000, phase="analyzing", source="planner", title="Event 3")
    e4 = ChestActivityEvent(id="4", tsMs=4000, phase="speaking", source="tts", title="Event 4")

    await bus.publish(e1)
    await bus.publish(e2)
    await bus.publish(e3)

    # Buffer should be full
    snapshot = await bus.snapshot()
    assert len(snapshot) == 3
    assert snapshot[0].id == "1"
    assert snapshot[2].id == "3"

    # Publish e4, it should pop e1
    await bus.publish(e4)
    snapshot = await bus.snapshot()
    assert len(snapshot) == 3
    assert snapshot[0].id == "2"
    assert snapshot[2].id == "4"


@pytest.mark.asyncio
async def test_activity_bus_subscription():
    """Verify that ActivityBus subscription queue receives published events."""
    bus = ActivityBus()
    queue = bus.subscribe()
    
    event = ChestActivityEvent(id="sub-1", tsMs=5000, phase="acting", source="planner", title="Sub Event")
    await bus.publish(event)
    
    # Pull from subscription queue
    received = await queue.get()
    assert received.id == "sub-1"
    assert received.phase == "acting"
    
    bus.unsubscribe(queue)


def test_chest_snapshot_endpoint():
    """Verify that GET /api/chest/snapshot returns correct serialized events."""
    bus = get_activity_bus()
    
    # Clear current snapshot buffer for testing
    bus.history.clear()
    
    event = ChestActivityEvent(
        id="snap-test",
        tsMs=123456,
        phase="listening",
        source="runtime",
        title="Testing Snapshot Endpoint",
        detail="No details",
        severity="info"
      )
    
    # We run the async publish in the event loop sync wrapper
    asyncio.run(bus.publish(event))
    
    response = client.get("/api/chest/snapshot")
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) >= 1
    assert data[-1]["id"] == "snap-test"
    assert data[-1]["phase"] == "listening"
    assert data[-1]["source"] == "runtime"
    assert data[-1]["title"] == "Testing Snapshot Endpoint"


def test_chest_browser_stream_endpoint():
    """Verify that GET /api/chest/browser/stream returns multipart stream headers."""
    response = client.get("/api/chest/browser/stream", stream=True)
    assert response.status_code == 200
    assert "multipart/x-mixed-replace" in response.headers["content-type"]
