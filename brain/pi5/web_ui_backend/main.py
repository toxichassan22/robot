import os
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import core as core_module
from .runtime_paths import get_app_root, get_frontend_dist_root


def __getattr__(name):
    return getattr(core_module, name)


app = core_module.app
REPO_ROOT = get_app_root(__file__, depth=3)
STATIC_DIR = Path(os.getenv("ROBOT_WEB_UI_DIST_PATH", str(get_frontend_dist_root(REPO_ROOT)))).resolve()
FRONTEND_HEADERS = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache", "Expires": "0"}


if not getattr(app.state, "web_ui_backend_initialized", False):
    from .routers import auth_settings  # noqa: F401
    from .routers import llm  # noqa: F401
    from .routers import motion  # noqa: F401
    from .routers import state  # noqa: F401
    from .routers import tts  # noqa: F401
    from .routers import camera # noqa: F401
    from .routers import api_keys  # noqa: F401

    if STATIC_DIR.exists():
        assets_dir = STATIC_DIR / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            if full_path.startswith("api/") or full_path.startswith("v1/"):
                raise HTTPException(status_code=404, detail="Not found")

            file_path = STATIC_DIR / full_path
            if full_path and file_path.is_file():
                return FileResponse(file_path, headers=FRONTEND_HEADERS)

            index_path = STATIC_DIR / "index.html"
            if index_path.exists():
                return FileResponse(index_path, headers=FRONTEND_HEADERS)

            raise HTTPException(status_code=404, detail="Frontend not built.")

    app.state.web_ui_backend_initialized = True


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
