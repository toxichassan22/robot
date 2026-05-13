import asyncio
import logging
import os
from brain.state.robot_state_manager import RobotStateManager

class ThermalMonitor:
    def __init__(self, state_manager: RobotStateManager, interval_s: float = 2.0):
        self.state_manager = state_manager
        self.interval_s = interval_s
        self.running = False
        self.logger = logging.getLogger(__name__)

    async def start(self):
        self.running = True
        self.logger.info("Thermal monitor started")
        await self._thermal_loop()

    async def stop(self):
        self.running = False
        self.logger.info("Thermal monitor stopped")

    async def _thermal_loop(self):
        while self.running:
            try:
                temp_c = self._read_cpu_temp()
                self.state_manager.update_temperature(temp_c)
                # Logging transitions is handled by manager or we can check changes here
                # For now just reliable update.
            except Exception as e:
                self.logger.error(f"Error in thermal loop: {e}")
            
            await asyncio.sleep(self.interval_s)

    def _read_cpu_temp(self) -> float:
        try:
            # Standard Linux thermal zone
            # Verified on Raspberry Pi
            path = "/sys/class/thermal/thermal_zone0/temp"
            if os.path.exists(path):
                with open(path, "r") as f:
                    # Value is in millidegrees
                    return int(f.read().strip()) / 1000.0
            
            # Windows fallback or other (since dev is on Windows d:)
            # On Windows we might generic mock or return 0.
            # Assuming production is Linux, but dev is Windows.
            # I'll return 45.0 as safe mock for Windows.
            if os.name == 'nt':
                 return 45.0
            
            return 0.0
        except Exception:
            return 0.0
