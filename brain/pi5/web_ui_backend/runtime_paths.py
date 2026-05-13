from __future__ import annotations

import os
import sys
from pathlib import Path


def get_app_root(source_file: str | Path, *, depth: int = 3) -> Path:
    explicit_root = str(os.getenv("ROBOT_APP_ROOT", "")).strip()
    if explicit_root:
        return Path(explicit_root).resolve()

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    path = Path(source_file).resolve()
    for _ in range(depth):
        path = path.parent
    return path


def get_frontend_dist_root(app_root: Path) -> Path:
    repo_dist = app_root / "pi5" / "web_ui" / "dist"
    if repo_dist.exists():
        return repo_dist
    return app_root / "dist"
