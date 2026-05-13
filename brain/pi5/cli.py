from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict

from brain.config import BrainConfig
from brain.types import PerceptionState, SensorPacket

def main() -> int:
    parser = argparse.ArgumentParser(prog="pi_5")
    sub = parser.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo")
    demo.add_argument("--steps", type=int, default=5)
    demo.add_argument("--ollama-model", type=str, default=None)

    say = sub.add_parser("say")
    say.add_argument("--text", action="append", default=[])
    say.add_argument("--ollama-model", type=str, default=None)

    listen = sub.add_parser("listen")
    listen.add_argument("--source", choices=["stdin", "mic"], default="stdin")
    listen.add_argument("--vosk-model-path", type=str, default=None)
    listen.add_argument("--tts", choices=["none", "pyttsx3", "gtts"], default="none")
    listen.add_argument("--ollama-model", type=str, default=None)

    vosk_check = sub.add_parser("vosk-check")
    vosk_check.add_argument("--vosk-model-path", type=str, required=True)

    vosk_find = sub.add_parser("vosk-find")
    vosk_find.add_argument("--root", action="append", default=[])
    vosk_find.add_argument("--max-depth", type=int, default=6)

    run = sub.add_parser("run")
    run.add_argument("--once", action="store_true")
    run.add_argument("--ollama-model", type=str, default=None)

    args = parser.parse_args()
    cfg = BrainConfig.from_env()

    if getattr(args, "ollama_model", None):
        cfg = cfg.with_ollama_model(args.ollama_model)

    if args.cmd == "vosk-check":
        from brain.pi5.ai.speech.vosk_stt import VoskMicListener

        listener = VoskMicListener(model_path=args.vosk_model_path)
        try:
            ok = listener.validate_model_path()
            print(ok)
            return 0
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1

    if args.cmd == "vosk-find":
        from brain.pi5.ai.speech.vosk_stt import find_vosk_models

        roots = list(args.root or [])
        if not roots:
            cwd = os.getcwd()
            roots = [os.path.join(cwd, "models"), cwd]
        found = find_vosk_models(roots=roots, max_depth=int(args.max_depth))
        if not found:
            print("No Vosk models found.")
            return 1
        for m in found:
            print(m)
        return 0

    from brain.runtime import BrainRuntime
    from brain.pi5.core.comms.build_transport import build_transport
    from brain.pi5.runtime import (
        run_demo,
        run_main_loop,
        run_mic_loop,
        run_say,
        run_stdin_loop,
    )

    transport = build_transport(cfg)
    runtime = BrainRuntime(cfg, transport=transport)

    if args.cmd == "demo":
        asyncio.run(run_demo(runtime, args.steps))
    elif args.cmd == "say":
        texts = list(args.text or [])
        if not texts:
            texts = ["hello", "aria hello"]
        asyncio.run(run_say(runtime, texts))
    elif args.cmd == "listen":
        tts_provider = args.tts
        if args.source == "stdin":
            asyncio.run(run_stdin_loop(runtime, tts_provider))
        else:
            vosk_path = args.vosk_model_path or cfg.vosk_model_path
            asyncio.run(run_mic_loop(runtime, vosk_path, tts_provider))
    elif args.cmd == "run":
        asyncio.run(run_main_loop(runtime, args.once))

    return 0

if __name__ == "__main__":
    sys.exit(main())
