from __future__ import annotations

import asyncio

from brain.transport.transport_base import Transport


class SerialTransport(Transport):
    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self._serial = None

    async def open(self) -> None:
        try:
            import serial  # type: ignore
        except Exception as e:
            raise RuntimeError("pyserial is required for serial transport") from e
        if not self.port:
            raise ValueError("BRAIN_ESP32_SERIAL_PORT is empty")
        self._serial = serial.Serial(self.port, self.baudrate, timeout=0)

    async def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
        self._serial = None

    async def write_line(self, line: str) -> None:
        if self._serial is None:
            raise RuntimeError("transport not open")
        self._serial.write((line + "\n").encode("utf-8"))
        await asyncio.sleep(0)

    async def read_line(self, timeout_s: float | None) -> str | None:
        if self._serial is None:
            raise RuntimeError("transport not open")

        async def _poll() -> str | None:
            data = self._serial.readline()
            return data.decode("utf-8").rstrip("\n") if data else None

        if timeout_s is None:
            while True:
                line = await _poll()
                if line is not None:
                    return line
                await asyncio.sleep(0.01)
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            line = await _poll()
            if line is not None:
                return line
            await asyncio.sleep(0.01)
        return None

