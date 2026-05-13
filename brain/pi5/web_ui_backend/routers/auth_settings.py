import secrets
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import core

app = core.app


def _public_robot_settings_payload(settings: core.RobotSettings) -> dict:
    return settings.model_dump(exclude={"robotPinHash"})


@app.post("/api/settings/auth")
async def auth(
    request: Request,
    x_robot_pin: Optional[str] = Header(None, alias=core.PIN_HEADER),
):
    ip = core.get_client_ip(request)
    try:
        core._check_pin_throttle(ip)
        effective_hash = await core._get_effective_pin_hash()
        if not effective_hash:
            if x_robot_pin is None:
                return JSONResponse(status_code=401, content={"error": "pin_not_configured"})
            if not core._pin_format_ok(x_robot_pin):
                core._record_pin_failure(ip)
                return JSONResponse(status_code=401, content={"error": "invalid_pin"})
            settings = await core.load_settings()
            settings.robotPinHash = core._pbkdf2_hash(x_robot_pin.strip())
            await core.save_settings(settings)
            effective_hash = settings.robotPinHash

        if x_robot_pin is None or not core._pin_format_ok(x_robot_pin) or not core._verify_pin_against_hash(x_robot_pin.strip(), effective_hash):
            core._record_pin_failure(ip)
            return JSONResponse(status_code=401, content={"error": "invalid_pin"})

        core._clear_pin_failures(ip)
        await core._maybe_migrate_bootstrap_pin_hash()
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"error": "rate_limited"})

    session_id = secrets.token_hex(16)
    session_expires = time.time() + core.SESSION_DURATION
    core.sessions[session_id] = session_expires
    return {"status": "ok", "sessionToken": session_id, "sessionExpiresAtMs": int(session_expires * 1000)}


@app.get("/api/settings/check-auth")
async def check_auth(session_id: str = Depends(core.get_current_session)):
    return {"status": "ok"}


@app.post("/api/settings/logout")
async def logout(x_robot_session: Optional[str] = Header(None, alias="x-robot-session")):
    if x_robot_session:
        core.sessions.pop(x_robot_session, None)
    return {"success": True}


@app.get("/api/settings")
async def get_settings(_auth: str = Depends(core.get_auth_dependency())):
    return await core.load_settings()


@app.post("/api/settings")
async def update_settings(settings: core.RobotSettings, _auth: str = Depends(core.get_auth_dependency())):
    await core.save_settings(settings)
    command_queue = core.get_command_queue()
    if command_queue is not None:
        await command_queue.put({"kind": "reload_settings", "payload": {}})
    return {"status": "ok"}


@app.get("/api/robot-settings")
async def get_robot_settings():
    settings = await core.load_settings()
    return {
        "success": True,
        "settings": _public_robot_settings_payload(settings),
    }


class RobotSettingsUpdateBody(BaseModel):
    settings: core.RobotSettings


@app.put("/api/robot-settings")
async def update_robot_settings(
    body: RobotSettingsUpdateBody,
    request: Request,
    x_robot_session: Optional[str] = Header(None, alias="x-robot-session"),
    x_robot_pin: Optional[str] = Header(None, alias=core.PIN_HEADER),
):
    session_token = core.get_valid_session_token(x_robot_session)
    if session_token:
        body.settings.robotPinHash = (await core.load_settings()).robotPinHash
        await core.save_settings(body.settings)
        command_queue = core.get_command_queue()
        if command_queue is not None:
            await command_queue.put({"kind": "reload_settings", "payload": {}})
        return {"success": True}

    if x_robot_pin is None:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    ip = core.get_client_ip(request)
    core._check_pin_throttle(ip)
    effective_hash = await core._get_effective_pin_hash()
    if not effective_hash:
        if not core._pin_format_ok(x_robot_pin):
            core._record_pin_failure(ip)
            raise HTTPException(status_code=401, detail={"error": "invalid_pin"})
        settings = await core.load_settings()
        settings.robotPinHash = core._pbkdf2_hash(x_robot_pin.strip())
        await core.save_settings(settings)
        effective_hash = settings.robotPinHash

    if not core._pin_format_ok(x_robot_pin) or not core._verify_pin_against_hash(x_robot_pin.strip(), effective_hash):
        core._record_pin_failure(ip)
        raise HTTPException(status_code=401, detail={"error": "invalid_pin"})

    core._clear_pin_failures(ip)
    await core._maybe_migrate_bootstrap_pin_hash()

    session_token = secrets.token_hex(16)
    session_expires = time.time() + core.SESSION_DURATION
    core.sessions[session_token] = session_expires

    body.settings.robotPinHash = (await core.load_settings()).robotPinHash
    await core.save_settings(body.settings)
    command_queue = core.get_command_queue()
    if command_queue is not None:
        await command_queue.put({"kind": "reload_settings", "payload": {}})

    return {
        "success": True,
        "sessionToken": session_token,
        "sessionExpiresAtMs": int(session_expires * 1000),
    }


@app.post("/api/admin/pin")
async def admin_set_pin(
    request: Request,
    x_robot_new_pin: Optional[str] = Header(None, alias="x-robot-new-pin"),
    _auth: str = Depends(core.get_auth_dependency()),
):
    if x_robot_new_pin is None or not core._pin_format_ok(x_robot_new_pin):
        raise HTTPException(status_code=400, detail={"error": "invalid_new_pin"})
    settings = await core.load_settings()
    settings.robotPinHash = core._pbkdf2_hash(x_robot_new_pin.strip())
    await core.save_settings(settings)
    return {"success": True}
