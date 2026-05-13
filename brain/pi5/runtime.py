from __future__ import annotations

import asyncio
import time

from brain.runtime import BrainRuntime
from brain.types import PerceptionState, SensorPacket
from brain.pi5.ai.speech.vosk_stt import VoskMicListener
from brain.pi5.ai.speech.tts import speak


async def get_tts_callback(runtime: BrainRuntime, tts_provider: str):
    async def tts_callback(txt: str):
        if tts_provider != "none":
            await speak(
                text=txt,
                provider=tts_provider,
                lang=runtime.cfg.robot_language,
                gender=runtime.cfg.tts_voice_gender,
                cache_dir=runtime.cfg.tts_cache_dir,
            )
    return tts_callback


async def run_demo(runtime: BrainRuntime, steps: int):
    await runtime.transport.open()
    try:
        for i in range(steps):
            pkt = SensorPacket(ts_ms=int(time.time() * 1000), values={"temp_c": 23 + i, "motion": bool(i % 2)})
            await runtime.esp32.send_sensor_packet(pkt)
            spoken = f"status {i}" if i != 1 else f"aria status {i}"
            perception = runtime.perceiver.from_inputs(text=spoken, vision=None, sensors=pkt.values, gestures=None)
            await runtime.handle_perception(perception, print_events=False, tts_callback=None)
            await asyncio.sleep(0.05)
    finally:
        await runtime.transport.close()


async def run_say(runtime: BrainRuntime, texts: list[str]):
    await runtime.transport.open()
    try:
        for t in texts:
            perception = runtime.perceiver.from_inputs(text=t, vision=None, sensors=None, gestures=None)
            await runtime.handle_perception(perception, print_events=True, tts_callback=None)
            await asyncio.sleep(0.01)
    finally:
        await runtime.transport.close()


async def run_stdin_loop(runtime: BrainRuntime, tts_provider: str):
    await runtime.transport.open()
    try:
        while True:
            try:
                text = await asyncio.to_thread(input, "> ")
            except (asyncio.CancelledError, KeyboardInterrupt):
                break
            except EOFError:
                break
            if not text.strip():
                continue
            if text.strip().lower() in {"quit", "exit"}:
                break
            perception = runtime.perceiver.from_inputs(text=text, vision=None, sensors=None, gestures=None)
            await runtime.handle_perception(perception, print_events=True, tts_callback=await get_tts_callback(runtime, tts_provider))
    finally:
        await runtime.transport.close()


async def run_mic_loop(runtime: BrainRuntime, vosk_model_path: str | None, tts_provider: str):
    await runtime.transport.open()
    listener = VoskMicListener(model_path=vosk_model_path)
    try:
        async for text in listener.stream_text():
            perception = runtime.perceiver.from_inputs(text=text, vision=None, sensors=None, gestures=None)
            await runtime.handle_perception(perception, print_events=True, tts_callback=await get_tts_callback(runtime, tts_provider))
    finally:
        await runtime.transport.close()


async def run_main_loop(runtime: BrainRuntime, once: bool = False):
    await runtime.transport.open()
    try:
        while True:
            sensors = await runtime.esp32.poll_sensors(timeout_s=0.5)
            perception = runtime.perceiver.from_inputs(text=None, vision=None, sensors=sensors, gestures=None)
            await runtime.handle_perception(perception, print_events=False, tts_callback=None)
            if once:
                break
    finally:
        await runtime.transport.close()
