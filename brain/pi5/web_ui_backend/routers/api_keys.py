"""API Keys management router — separate PIN-protected endpoints.

Provides CRUD operations for HuggingFace API keys used by the robot brain.
Protected by a **separate** PIN (ROBOT_API_KEYS_PIN) distinct from the
main dashboard PIN.
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .. import core

app = core.app

# Path to the HF keys JSON file — always resolve relative to project root
REPO_ROOT = core.REPO_ROOT
_hf_keys_env = os.getenv("BRAIN_HF_KEYS_FILE", "")
if _hf_keys_env:
    _hf_keys_path = Path(_hf_keys_env)
    HF_KEYS_FILE = _hf_keys_path if _hf_keys_path.is_absolute() else (REPO_ROOT / _hf_keys_path).resolve()
else:
    HF_KEYS_FILE = (REPO_ROOT / "config" / "data" / "hf_keys.json").resolve()

# ── Serve the keys.html page ────────────────────────────────────────
_KEYS_HTML_PATH = REPO_ROOT / "dashboard" / "dist" / "keys.html"

@app.get("/keys.html", response_class=HTMLResponse)
async def serve_keys_page():
    """Serve the secret API keys management page."""
    if _KEYS_HTML_PATH.exists():
        return HTMLResponse(content=_KEYS_HTML_PATH.read_text(encoding="utf-8"))
    # Fallback: try relative to project root
    alt = Path(__file__).resolve().parent.parent.parent.parent.parent / "dashboard" / "dist" / "keys.html"
    if alt.exists():
        return HTMLResponse(content=alt.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="keys.html not found")

# ── Separate PIN for API Keys page ───────────────────────────────────
API_KEYS_PIN = os.getenv("ROBOT_API_KEYS_PIN", "992006").strip()
API_KEYS_SESSION_DURATION = 3600  # 1 hour
_api_keys_sessions: Dict[str, float] = {}
_api_keys_rate_limit: Dict[str, Dict[str, float]] = {}

# Lazy-loaded key manager instance
_key_manager = None


def _get_key_manager():
    """Get or create the HFKeyManager singleton."""
    global _key_manager
    if _key_manager is None:
        from brain.llm.hf_key_manager import HFKeyManager
        _key_manager = HFKeyManager(str(HF_KEYS_FILE))
    return _key_manager


def set_key_manager(manager) -> None:
    """Allow runtime to inject a shared key manager instance."""
    global _key_manager
    _key_manager = manager


# ── Auth helpers (separate from main dashboard auth) ─────────────────

def _api_keys_rate_state(ip: str) -> Dict[str, float]:
    state = _api_keys_rate_limit.get(ip)
    if not isinstance(state, dict):
        state = {"windowStart": time.time(), "fails": 0.0, "lockUntil": 0.0}
        _api_keys_rate_limit[ip] = state
    return state


def _check_api_keys_throttle(ip: str) -> None:
    now = time.time()
    state = _api_keys_rate_state(ip)
    if float(state.get("lockUntil", 0.0)) > now:
        retry_after = max(1, int(float(state["lockUntil"]) - now))
        raise HTTPException(status_code=429, detail={"error": "rate_limited", "retryAfterSec": retry_after})
    if now - float(state.get("windowStart", now)) > 300.0:
        _api_keys_rate_limit.pop(ip, None)


def _record_api_keys_failure(ip: str) -> None:
    now = time.time()
    state = _api_keys_rate_state(ip)
    if now - float(state.get("windowStart", now)) > 300.0:
        state["windowStart"] = now
        state["fails"] = 0.0
    state["fails"] = float(state.get("fails", 0.0)) + 1.0
    if state["fails"] >= 5.0:
        state["lockUntil"] = now + 60.0  # Lock for 60s after 5 failures


def _verify_api_keys_session(token: Optional[str]) -> bool:
    if not token:
        return False
    expiry = _api_keys_sessions.get(token)
    if not expiry:
        return False
    if time.time() > expiry:
        _api_keys_sessions.pop(token, None)
        return False
    return True


async def _require_api_keys_auth(
    request: Request,
    x_api_keys_session: Optional[str] = None,
    x_api_keys_pin: Optional[str] = None,
) -> None:
    """Verify API keys page auth — session token or PIN."""
    if _verify_api_keys_session(x_api_keys_session):
        return

    if not x_api_keys_pin:
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})

    ip = core.get_client_ip(request)
    _check_api_keys_throttle(ip)

    if x_api_keys_pin.strip() != API_KEYS_PIN:
        _record_api_keys_failure(ip)
        raise HTTPException(status_code=401, detail={"error": "invalid_pin"})

    _api_keys_rate_limit.pop(ip, None)


# ── Pydantic models ─────────────────────────────────────────────────

class AuthPinBody(BaseModel):
    pin: str


class AddKeyBody(BaseModel):
    key: str
    label: str = ""


class ReorderBody(BaseModel):
    key_ids: List[str]


class ModelsBody(BaseModel):
    primary: str = ""
    fallback: str = ""


# ── Routes ───────────────────────────────────────────────────────────

@app.post("/api/keys/auth")
async def api_keys_auth(body: AuthPinBody, request: Request):
    """Authenticate with the API keys PIN (separate from dashboard PIN)."""
    ip = core.get_client_ip(request)
    try:
        _check_api_keys_throttle(ip)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    if body.pin.strip() != API_KEYS_PIN:
        _record_api_keys_failure(ip)
        return JSONResponse(status_code=401, content={"error": "invalid_pin"})

    _api_keys_rate_limit.pop(ip, None)
    session_id = secrets.token_hex(16)
    session_expires = time.time() + API_KEYS_SESSION_DURATION
    _api_keys_sessions[session_id] = session_expires
    return {
        "status": "ok",
        "sessionToken": session_id,
        "sessionExpiresAtMs": int(session_expires * 1000),
    }


@app.get("/api/keys/list")
async def api_keys_list(
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Get all API keys with their status."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    manager = _get_key_manager()
    return {"keys": manager.get_all_keys_status()}


@app.get("/api/keys/status")
async def api_keys_status(
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Get overall system status."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    manager = _get_key_manager()
    return manager.get_status_summary()


@app.post("/api/keys/add")
async def api_keys_add(
    body: AddKeyBody,
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Add a new API key."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    if not body.key.strip():
        raise HTTPException(status_code=400, detail={"error": "key_required"})
    manager = _get_key_manager()
    result = manager.add_key(body.key, body.label)
    return {"status": "ok", **result}


@app.delete("/api/keys/{key_id}")
async def api_keys_remove(
    key_id: str,
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Remove an API key."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    manager = _get_key_manager()
    if manager.remove_key(key_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail={"error": "key_not_found"})


@app.post("/api/keys/{key_id}/reset")
async def api_keys_reset(
    key_id: str,
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Re-activate an exhausted/disabled key."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    manager = _get_key_manager()
    if manager.reset_key(key_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail={"error": "key_not_found"})


@app.post("/api/keys/{key_id}/disable")
async def api_keys_disable(
    key_id: str,
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Manually disable a key."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    manager = _get_key_manager()
    if manager.disable_key(key_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail={"error": "key_not_found"})


@app.put("/api/keys/reorder")
async def api_keys_reorder(
    body: ReorderBody,
    request: Request,
    x_api_keys_session: Optional[str] = Header(None, alias="x-api-keys-session"),
):
    """Reorder API keys (drag-and-drop from UI)."""
    await _require_api_keys_auth(request, x_api_keys_session=x_api_keys_session)
    manager = _get_key_manager()
    manager.reorder_keys(body.key_ids)
    return {"status": "ok"}
