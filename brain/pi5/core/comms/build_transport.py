from __future__ import annotations

from brain.config import BrainConfig
from brain.transport.transport_base import Transport
from brain.transport.transport_mock import MockTransport
from brain.pi5.core.comms.esp32.transport_tcp import TcpTransport
from brain.pi5.core.comms.serial.transport_serial import SerialTransport


def build_transport(cfg: BrainConfig) -> Transport:
    kind = (cfg.transport or "mock").lower()
    if kind == "mock":
        return MockTransport()
    if kind == "tcp":
        return TcpTransport(host=cfg.esp32_tcp_host, port=cfg.esp32_tcp_port)
    if kind == "serial":
        return SerialTransport(port=cfg.esp32_serial_port, baudrate=cfg.esp32_serial_baud)
    raise ValueError(f"Unknown transport: {cfg.transport}")

