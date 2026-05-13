"""
chat_with_robot.py — شات تفاعلي مع الروبوت (كتابة → صوت)

هذا الملف يختبر **دورة حياة العقل بالكامل** 
(Brain Pipeline: Perception -> State -> Planner -> Safe Executor) 
باستخدام مدخلات نصية. استخدمه لاختبار قرارات الروبوت وقواعد الأمان.

Usage:
  python brain/chat_with_robot.py
"""
import sys
import os
import asyncio
import time

# === Path Setup ===
# brain/ is this file's directory; project root is one level up
BRAIN_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BRAIN_DIR)

# Add project root so 'brain' package is importable
sys.path.insert(0, PROJECT_ROOT)

# === Load .env from config/ ===
env_path = os.path.join(PROJECT_ROOT, 'config', '.env')
if os.path.exists(env_path):
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                os.environ.setdefault(key.strip(), val.strip())

# Force XTTS
os.environ["BRAIN_TTS_PROVIDER"] = "xtts"

# === Imports ===
from brain.config import BrainConfig
from brain.runtime import BrainRuntime
from brain.types import PerceptionState
from brain.transport.transport_mock import MockTransport


class ChatRuntime(BrainRuntime):
    """Simplified BrainRuntime for text chat + TTS output"""

    def __init__(self, cfg, transport):
        super().__init__(cfg, transport)
        self._input_q: asyncio.Queue = asyncio.Queue()

    async def _input_loop(self):
        print("\n" + "=" * 50)
        print("💬 Chat with Robot (type 'exit' to quit)")
        print("=" * 50)
        loop = asyncio.get_running_loop()
        while True:
            text = await loop.run_in_executor(None, input, "\nYou: ")
            text = text.strip()
            if text.lower() in ("exit", "quit"):
                print("👋 Bye!")
                os._exit(0)
            if text:
                await self._input_q.put(text)

    async def run_chat(self):
        # Start TTS engine (loads XTTS model in background thread)
        print("🔄 Starting TTS engine...")
        self.tts.start()

        # Force wake-word gate to be awake (we are chatting directly)
        self.gate.is_awake = True

        # Start background tasks
        asyncio.create_task(self.process_commands())
        asyncio.create_task(self._input_loop())

        print(f"🤖 TTS Provider: {self.tts.__class__.__name__}")
        print("⏳ Waiting for XTTS model to load (first time takes ~30s)...")

        while True:
            text = await self._input_q.get()
            perception = PerceptionState(
                ts_ms=int(time.time() * 1000),
                text=text,
                vision=None,
                sensors=None,
                gestures=None,
            )
            print(f"🤖 Thinking...")

            async def tts_say(reply_text):
                """Callback: Brain calls this to speak"""
                print(f"🔊 Robot: {reply_text}")
                self.tts.say(reply_text)

            await self.handle_perception(
                perception,
                print_events=False,
                tts_callback=tts_say,
            )


def main():
    config = BrainConfig.from_env()
    transport = MockTransport()
    runtime = ChatRuntime(config, transport)

    try:
        asyncio.run(runtime.run_chat())
    except KeyboardInterrupt:
        print("\n👋 Stopped.")


if __name__ == "__main__":
    main()
