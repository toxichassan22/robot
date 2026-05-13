from __future__ import annotations

import abc


class Transport(abc.ABC):
    @abc.abstractmethod
    async def open(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def close(self) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def write_line(self, line: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    async def read_line(self, timeout_s: float | None) -> str | None:
        raise NotImplementedError

