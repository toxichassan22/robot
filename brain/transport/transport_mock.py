from __future__ import annotations

import asyncio
import json
import time

from brain.transport.transport_base import Transport


class MockTransport(Transport):
    def __init__(self) -> None:
        self._rx: asyncio.Queue[str] = asyncio.Queue()
        self._open = False

    async def open(self) -> None:
        self._open = True

    async def close(self) -> None:
        self._open = False
        while not self._rx.empty():
            self._rx.get_nowait()

    async def write_line(self, line: str) -> None:
        msg = json.loads(line)
        if msg.get("type") == "poll_sensors":
            reply = {"type": "sensors", "ts_ms": int(time.time() * 1000), "values": {"temp_c": 24.0, "motion": False}}
            await self._rx.put(json.dumps(reply))
        elif msg.get("type") == "heartbeat":
            reply = {"type": "heartbeat_ack", "ts_ms": int(time.time() * 1000), "ref": msg.get("type")}
            await self._rx.put(json.dumps(reply))
        else:
            ack = {"type": "ack", "ts_ms": int(time.time() * 1000), "ref": msg.get("type")}
            await self._rx.put(json.dumps(ack))

    async def read_line(self, timeout_s: float | None) -> str | None:
        if timeout_s is None:
            return await self._rx.get()
        try:
            return await asyncio.wait_for(self._rx.get(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None
