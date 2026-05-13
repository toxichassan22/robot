import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["GLOG_minloglevel"] = "2"
os.environ["GLOG_logtostderr"] = "0"

import argparse
import asyncio
import json
import sys
from brain.config import BrainConfig

def main() -> int:
    parser = argparse.ArgumentParser(prog="brain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    models = sub.add_parser("ollama-models")
    models.add_argument("--base-url", type=str, default=None)
    models.add_argument("--json", action="store_true")

    run_parser = sub.add_parser("run")

    args = parser.parse_args()
    cfg = BrainConfig.from_env()

    if args.cmd == "ollama-models":
        from brain.llm.ollama_client import OllamaClient

        base_url = args.base_url or cfg.ollama_base_url
        client = OllamaClient(base_url=base_url)
        try:
            models_list = client.list_models()
        except Exception as e:
            print(f"Failed to query Ollama at {base_url}: {e}", file=sys.stderr)
            return 1

        if args.json:
            print(json.dumps(models_list, ensure_ascii=False, indent=2))
        else:
            for m in models_list:
                print(m)
        return 0

    if args.cmd == "run":
        from brain.runtime import BrainRuntime

        if cfg.transport == "serial":
            from brain.transport.serial_transport import SerialTransport
            # If port is empty, SerialTransport will attempt auto-detect if we pass "auto" or empty
            # But let's respect the config. 
            port = cfg.esp32_serial_port or "auto"
            try:
                transport = SerialTransport(port=port, baud=cfg.esp32_serial_baud)
                # SerialTransport.open is async, we will call it inside runtime or just let it open on first usage? 
                # TransportBase says open() is async. BrainRuntime doesn't seem to call open() explicitly in __init__.
                # We should open it.
                # Actually BrainRuntime doesn't call open() in the previous code I saw. 
                # Let's check runtime.py again. 
                # The runtime probably assumes it's ready or we need to open it here or in runtime.run()
                # Ideally runtime should manage lifecycle.
                # For now let's pass it to runtime.
            except Exception as e:
                print(f"Failed to create SerialTransport: {e}", file=sys.stderr)
                return 1
        else:
            from brain.transport.transport_mock import MockTransport
            transport = MockTransport()

        runtime = BrainRuntime(cfg, transport=transport)
        
        # We need to ensure transport is opened. 
        # Modifying BrainRuntime to open transport would be cleaner, but for now let's do it in run() wrapper or assume runtime does it.
        # Checking runtime.py... it doesn't seem to call Transport.open().
        # I should probably add transport.open() to BrainRuntime.run().
        
        try:
            # We will handle transport open/close here or inside runtime.
            # Let's modify usage below.
            async def _run_safe():
                 await transport.open()
                 try:
                     await runtime.run()
                 finally:
                     await transport.close()

            asyncio.run(_run_safe())
        
        except KeyboardInterrupt:
            print("Stopping...")
        except Exception as e:
            print(f"Runtime error: {e}", file=sys.stderr)
            return 1
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
