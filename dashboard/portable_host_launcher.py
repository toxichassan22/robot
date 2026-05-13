from __future__ import annotations

import asyncio
import atexit
import os
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
SD_ROOT = APP_ROOT / "sd"
RUN_ROOT = APP_ROOT / "run"
PID_PATH = Path(os.getenv("ROBOT_PID_PATH", str(RUN_ROOT / "robot_host.pid"))).resolve()

if str(SD_ROOT) not in sys.path:
    sys.path.insert(0, str(SD_ROOT))

os.environ.setdefault("ROBOT_APP_ROOT", str(APP_ROOT))
os.environ.setdefault("ROBOT_WEB_UI_DIST_PATH", str(APP_ROOT / "dist"))
os.environ.setdefault("ROBOT_SETTINGS_PATH", str(APP_ROOT / "data" / "robot_settings.json"))
os.environ.setdefault("BRAIN_MEMORY_DB_PATH", str(APP_ROOT / "data" / "brain.sqlite"))
os.environ.setdefault("ROBOT_MOTION_LOG_PATH", str(APP_ROOT / "data" / "motion_commands.jsonl"))
os.environ.setdefault("BRAIN_VOSK_MODEL_PATH", str(APP_ROOT / "data" / "vosk-model"))
os.environ.setdefault("ROBOT_HOST_MODE", "auto")
os.environ.setdefault("ROBOT_PID_PATH", str(PID_PATH))


def _write_pid() -> None:
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _clear_pid() -> None:
    try:
        if not PID_PATH.exists():
            return
        if PID_PATH.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_PATH.unlink()
    except Exception:
        pass


async def _run() -> None:
    from brain.config import BrainConfig
    from brain.runtime import BrainRuntime
    from pi_5.core.comms.build_transport import build_transport

    cfg = BrainConfig.from_env()
    transport = build_transport(cfg)
    runtime = BrainRuntime(cfg, transport=transport)

    await transport.open()
    try:
        await runtime.run()
    finally:
        await transport.close()


def main() -> None:
    _write_pid()
    atexit.register(_clear_pid)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
