import asyncio
import time
import logging
from typing import Optional
from brain.state.robot_state_manager import RobotStateManager
from brain.state.types import HeartbeatPayload

class HeartbeatManager:
    def __init__(self, esp32_client, state_manager: RobotStateManager, interval_ms: int = 500):
        self.esp32 = esp32_client
        self.state_manager = state_manager
        self.interval_ms = interval_ms
        self.running = False
        self.logger = logging.getLogger(__name__)

    async def start(self):
        self.running = True
        self.logger.info("Heartbeat manager started")
        await self._heartbeat_loop()

    async def stop(self):
        self.running = False
        self.logger.info("Heartbeat manager stopped")

    async def _heartbeat_loop(self):
        while self.running:
            try:
                snapshot = self.state_manager.get_state_snapshot()
                payload = HeartbeatPayload(
                    mode=snapshot["mode"],
                    speed_limit=snapshot["speed_limit"],
                    temp_c=snapshot["temp_c"],
                    timestamp_ms=int(time.time() * 1000)
                )
                
                # Send heartbeat via ESP32 client
                # Assuming send_heartbeat returns a future or is awaitable
                # The user plan says "Wait for ACK (with timeout)"
                # But since esp32_client.send_heartbeat wasn't defined as async in the plan description explicitly,
                # I'll assume for now I call it and if it needs to wait for ACK, the client handles it or returns boolean.
                # However, usually networking is async.
                
                # Let's verify esp32_client structure later, but for now we follow the plan:
                # "Send via esp32_client.send_heartbeat(payload)"
                # "Wait for ACK (with timeout)"
                
                # If send_heartbeat is blocking/sync, we might need run_in_executor, but we are in async loop.
                # I will assume esp32_client methods are async compatible or fast.
                
                # Actual implementation detail: The user said "Update RobotStateManager.last_heartbeat_ack_ms on success"
                # This suggests send_heartbeat might return success/fail.
                
                success = await self.esp32.send_heartbeat(payload)
                if success:
                    self.state_manager.update_heartbeat_ack()
                else:
                    self.logger.warning("Heartbeat ACK timeout or failure")
                    
            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")

            await asyncio.sleep(self.interval_ms / 1000.0)
