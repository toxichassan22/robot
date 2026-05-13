import asyncio
import warnings

from fastapi.routing import APIRoute
from starlette.requests import Request
from unittest.mock import AsyncMock, patch

from pi_5.web_ui_backend import core
from pi_5.web_ui_backend.main import app


def _build_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/motion/stop",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        }
    )


def test_get_auth_dependency_delegates_to_require_robot_auth():
    dependency = core.get_auth_dependency()
    request = _build_request()
    auth_mock = AsyncMock(return_value="patched")

    with patch.object(core, "require_robot_auth", auth_mock):
        result = asyncio.run(
            dependency(
                request=request,
                session_cookie=None,
                x_robot_session=None,
                x_robot_pin=None,
            )
        )

    assert result == "patched"
    auth_mock.assert_awaited_once()


def test_require_robot_auth_dependency_warns():
    request = _build_request()
    auth_mock = AsyncMock(return_value="patched")

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        with patch.object(core, "require_robot_auth", auth_mock):
            result = asyncio.run(
                core.require_robot_auth_dependency(
                    request=request,
                    session_cookie=None,
                    x_robot_session=None,
                    x_robot_pin=None,
                )
            )

    assert result == "patched"
    assert any("deprecated" in str(item.message).lower() for item in captured)


def test_protected_routes_use_canonical_auth_dependency():
    protected_routes = {
        ("/api/settings", "GET"),
        ("/api/settings", "POST"),
        ("/api/ai/wake", "POST"),
        ("/api/ai/wake", "PUT"),
        ("/api/motion/calibrate", "POST"),
        ("/api/motion/calibrate", "PUT"),
        ("/api/motion/move", "PUT"),
        ("/api/motion/stop", "PUT"),
        ("/api/motion/halt", "PUT"),
        ("/api/ai/override", "POST"),
        ("/api/ai/override", "PUT"),
        ("/api/motion/halt", "POST"),
        ("/api/motion/stop", "POST"),
        ("/api/mode", "POST"),
        ("/v1/commands", "POST"),
    }
    dependency = core.get_auth_dependency()

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        route_methods = set(route.methods or [])
        if not any((route.path, method) in protected_routes for method in route_methods):
            continue
        calls = [item.call for item in route.dependant.dependencies]
        assert dependency in calls
