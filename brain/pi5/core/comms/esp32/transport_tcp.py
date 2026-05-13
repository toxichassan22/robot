from __future__ import annotations

import asyncio
from asyncio import StreamReader, StreamWriter

from brain.transport.transport_base import Transport


class TcpTransport(Transport):
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._reader: StreamReader | None = None
        self._writer: StreamWriter | None = None

    async def open(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            await self._writer.wait_closed()
        self._reader = None
        self._writer = None

    async def write_line(self, line: str) -> None:
        if self._writer is None:
            raise RuntimeError("transport not open")
        self._writer.write((line + "\n").encode("utf-8"))
        await self._writer.drain()

    async def read_line(self, timeout_s: float | None) -> str | None:
        if self._reader is None:
            raise RuntimeError("transport not open")
        if timeout_s is None:
            data = await self._reader.readline()
            return data.decode("utf-8").rstrip("\n") if data else None
        try:
            data = await asyncio.wait_for(self._reader.readline(), timeout=timeout_s)
            return data.decode("utf-8").rstrip("\n") if data else None
        except asyncio.TimeoutError:
            return None

