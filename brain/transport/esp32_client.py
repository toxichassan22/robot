from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict

from brain.transport.transport_base import Transport
from brain.types import ActionCommand, MotionCommand, SensorPacket, ServoCommand
from brain.state.types import HeartbeatPayload


class Esp32Client:
    def __init__(self, transport: Transport):
        self.transport = transport

    async def send_action(self, cmd: ActionCommand) -> None:
        msg = {"type": "action", "ts_ms": int(time.time() * 1000), "action": asdict(cmd)}
        try:
            await self.transport.write_line(json.dumps(msg, ensure_ascii=False))
        except Exception as e:
            logging.error(f"ESP32: Failed to send action: {e}")

    async def poll_sensors(self, timeout_s: float = 0.5) -> dict:
        msg = {"type": "poll_sensors", "ts_ms": int(time.time() * 1000)}
        try:
            await self.transport.write_line(json.dumps(msg))
            line = await self.transport.read_line(timeout_s=timeout_s)
            if not line:
                return {}
            data = json.loads(line)
            if data.get("type") == "sensors":
                return data.get("values") or {}
        except Exception as e:
            logging.error(f"ESP32: Sensor poll failed: {e}")
        return {}

    async def send_sensor_packet(self, pkt: SensorPacket) -> None:
        msg = {"type": "sensors", **asdict(pkt)}
        try:
            await self.transport.write_line(json.dumps(msg))
        except Exception as e:
            logging.error(f"ESP32: Failed to send sensor packet: {e}")

    async def send_motion_command(self, cmd: MotionCommand) -> None:
        msg = {"type": "motion", "ts_ms": int(time.time() * 1000), "motion": asdict(cmd)}
        try:
            await self.transport.write_line(json.dumps(msg, ensure_ascii=False))
        except Exception as e:
            logging.error(f"ESP32: Failed to send motion command: {e}")

    async def send_servo_command(self, servo_id: int, angle: float) -> None:
        cmd = ServoCommand(servo_id=int(servo_id), angle=float(angle))
        msg = {"type": "servo", "ts_ms": int(time.time() * 1000), "servo": asdict(cmd)}
        try:
            await self.transport.write_line(json.dumps(msg, ensure_ascii=False))
        except Exception as e:
            logging.error(f"ESP32: Failed to send servo command: {e}")

    async def get_obstacle_distance(self, timeout_s: float = 0.5) -> float | None:
        msg = {"type": "get_obstacle_distance", "ts_ms": int(time.time() * 1000)}
        try:
            await self.transport.write_line(json.dumps(msg))
            line = await self.transport.read_line(timeout_s=timeout_s)
            if not line:
                return None
            data = json.loads(line)
            if data.get("type") == "obstacle_distance":
                v = data.get("cm")
                if isinstance(v, (int, float)):
                    return float(v)
        except Exception as e:
            logging.error(f"ESP32: Failed to get obstacle distance: {e}")
        return None

    async def send_heartbeat(self, payload: HeartbeatPayload) -> bool:
        """
        Sends a heartbeat message and expects a 'heartbeat_ack' response.
        Returns True if ACK is received within timeout, False otherwise.
        """
        msg = {
            "type": "heartbeat",
            "mode": payload.mode,
            "speed_limit": payload.speed_limit,
            "temp_c": payload.temp_c,
            "ts_ms": payload.timestamp_ms
        }
        try:
            await self.transport.write_line(json.dumps(msg))
            # We enforce a short timeout for heartbeat ACK (e.g. 0.5s or 1.0s)
            line = await self.transport.read_line(timeout_s=1.0)
            if not line:
                return False
            data = json.loads(line)
            if data.get("type") == "heartbeat_ack":
                return True
        except Exception:
            return False
        return False

    async def ping(self) -> bool:
        """
        Send a ping and expect a pong. Uses the transport's health_check if available,
        otherwise falls back to manual ping/pong.
        """
        if hasattr(self.transport, 'health_check'):
            return await self.transport.health_check()
        
        try:
            msg = json.dumps({"type": "ping", "ts_ms": int(time.time() * 1000)})
            await self.transport.write_line(msg)
            line = await self.transport.read_line(timeout_s=2.0)
            if line:
                data = json.loads(line)
                return data.get("type") == "pong"
        except Exception as e:
            logging.debug(f"ESP32 ping failed: {e}")
        return False

    @property
    def is_connected(self) -> bool:
        """Check if the transport reports a connected state."""
        if hasattr(self.transport, 'is_connected'):
            return self.transport.is_connected
        return True  # Assume connected for transports without this property
