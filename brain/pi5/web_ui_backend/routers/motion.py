import json
import sqlite3
import time

from fastapi import Depends, Query

from .. import core

app = core.app


def _motion_ack(command_type: str, issued_at_ms: int, payload: dict | None = None) -> dict:
    command_queue = core.get_command_queue()
    queued = command_queue is not None
    return {
        "success": True,
        "accepted": True,
        "queued": queued,
        "commandType": command_type,
        "commandId": f"{command_type}-{issued_at_ms}",
        "queuedAtMs": issued_at_ms,
        "payload": payload or {},
    }


@app.post("/api/feedback")
async def post_feedback(body: core.FeedbackBody):
    interaction_id = body.interactionId or str(int(time.time() * 1000))
    rating = 1 if body.rating and body.rating > 0 else 0
    correction = body.correction or ""
    context_json = json.dumps(body.context or {})
    ts_ms = int(time.time() * 1000)

    try:
        conn = sqlite3.connect(core.MEMORY_DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL, interaction_id TEXT NOT NULL, rating INTEGER NOT NULL, correction TEXT NOT NULL, context TEXT NOT NULL)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts_ms)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_interaction ON feedback(interaction_id)")
        conn.execute(
            "INSERT INTO feedback(ts_ms, interaction_id, rating, correction, context) VALUES (?, ?, ?, ?, ?)",
            (ts_ms, interaction_id, rating, correction, context_json),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:200]}


@app.api_route("/api/motion/move", methods=["POST", "PUT"])
async def move(body: core.MotionBody, _auth: str = Depends(core.get_auth_dependency())):
    issued_at_ms = int(time.time() * 1000)
    await core.append_motion_log(
        {
            "ts": issued_at_ms,
            "type": "motion",
            "direction": body.direction,
            "speed": body.speed,
            "durationMs": body.durationMs,
        }
    )
    return _motion_ack(
        "motion",
        issued_at_ms,
        {
            "direction": body.direction,
            "speed": body.speed,
            "durationMs": body.durationMs,
        },
    )


async def _record_stop_motion() -> None:
    await core.append_motion_log({"ts": int(time.time() * 1000), "type": "stop"})


@app.api_route("/api/motion/servo", methods=["POST", "PUT"])
async def servo(body: core.ServoBody, _auth: str = Depends(core.get_auth_dependency())):
    issued_at_ms = int(time.time() * 1000)
    await core.append_motion_log(
        {
            "ts": issued_at_ms,
            "type": "servo",
            "servoId": body.servoId,
            "angle": body.angle,
        }
    )
    return _motion_ack("servo", issued_at_ms, {"servoId": body.servoId, "angle": body.angle})


@app.api_route("/api/motion/stop", methods=["POST", "PUT"])
async def stop_motion(_auth: str = Depends(core.get_auth_dependency())):
    issued_at_ms = int(time.time() * 1000)
    await _record_stop_motion()
    return _motion_ack("stop", issued_at_ms)


@app.api_route("/api/motion/halt", methods=["POST", "PUT"])
async def halt_motion(_auth: str = Depends(core.get_auth_dependency())):
    issued_at_ms = int(time.time() * 1000)
    await _record_stop_motion()
    return _motion_ack("halt", issued_at_ms)


@app.api_route("/api/motion/calibrate", methods=["POST", "PUT"])
async def calibrate_motion(_auth: str = Depends(core.get_auth_dependency())):
    issued_at_ms = int(time.time() * 1000)
    entry = {
        "ts": issued_at_ms,
        "type": "servo",
        "servoId": 0,
        "angle": 90.0,
    }
    await core.append_motion_log(entry)
    return _motion_ack("calibrate", issued_at_ms, {"servoId": entry["servoId"], "angle": entry["angle"]})


@app.get("/api/safety-events")
async def get_safety_events(limit: int | None = Query(default=None, ge=1, le=50)):
    events = core.SAFETY_EVENTS[-limit:] if limit else core.SAFETY_EVENTS
    return {"success": True, "events": events}


@app.post("/api/safety-events")
async def log_safety_event(body: core.SafetyEventBody):
    core.SAFETY_EVENTS.append(body.model_dump())
    if len(core.SAFETY_EVENTS) > core.MAX_SAFETY_EVENTS:
        core.SAFETY_EVENTS.pop(0)
    return {"success": True}
