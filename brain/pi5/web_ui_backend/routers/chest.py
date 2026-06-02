from fastapi import Request
from fastapi.responses import StreamingResponse
import asyncio
import os
import json

from .. import core
from brain.activity.bus import get_activity_bus
from brain.agent_tools.visual_browser import get_visual_browser

app = core.app

def event_to_dict(e) -> dict:
    return {
        "id": e.id,
        "tsMs": e.tsMs,
        "phase": e.phase,
        "source": e.source,
        "title": e.title,
        "detail": e.detail,
        "progress": e.progress,
        "severity": e.severity,
        "emotion": e.emotion,
        "artifacts": e.artifacts,
        "analysis": e.analysis,
        "action": e.action
    }

@app.get("/api/chest/snapshot")
async def get_chest_snapshot():
    bus = get_activity_bus()
    snap = await bus.snapshot()
    return [event_to_dict(e) for e in snap]

@app.get("/api/chest/events")
async def get_chest_events(request: Request):
    bus = get_activity_bus()
    queue = bus.subscribe()

    async def event_generator():
        try:
            # 1. Send snapshot first as "snapshot" event
            snapshot = await bus.snapshot()
            snapshot_data = [event_to_dict(e) for e in snapshot]
            yield f"event: snapshot\ndata: {json.dumps(snapshot_data, ensure_ascii=False)}\n\n"

            # 2. Consume events and send periodic heartbeats
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"event: activity\ndata: {json.dumps(event_to_dict(event), ensure_ascii=False)}\n\n"
                    queue.task_done()
                except asyncio.TimeoutError:
                    yield "event: heartbeat\ndata: {}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def browser_frame_generator():
    browser_service = get_visual_browser()
    fps = float(os.getenv("ROBOT_CHEST_BROWSER_FPS", "6"))
    interval = 1.0 / fps
    while True:
        try:
            jpg = await browser_service.screenshot_jpeg()
            if jpg:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpg + b'\r\n')
        except Exception:
            pass
        await asyncio.sleep(interval)

@app.get("/api/chest/browser/stream")
async def browser_stream():
    return StreamingResponse(browser_frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

from pydantic import BaseModel

class ChestChatBody(BaseModel):
    text: str

@app.post("/api/chest/chat")
async def post_chest_chat(body: ChestChatBody):
    command_queue = core.get_command_queue()
    if command_queue is not None:
        await command_queue.put({"kind": "hearing", "payload": {"text": body.text}})
        return {"success": True}
    return {"success": False, "error": "command_queue_unavailable"}
