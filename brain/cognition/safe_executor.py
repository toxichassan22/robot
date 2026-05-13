import json
import logging
import time
from dataclasses import asdict
from typing import Any
from brain.transport.esp32_client import Esp32Client
from brain.state.robot_state_manager import RobotStateManager
from brain.cognition.safety.behavior_tree import BehaviorTree
from brain.state.types import ValidationResult
from brain.types import MotionCommand, ServoCommand

class SafeCommandExecutor:
    def __init__(self, esp32_client: Esp32Client, state_manager: RobotStateManager, behavior_tree: BehaviorTree):
        self.esp32 = esp32_client
        self.state_manager = state_manager
        self.behavior_tree = behavior_tree
        self.logger = logging.getLogger(__name__)

    async def execute(self, command: Any) -> ValidationResult:
        """
        Execute an action command safely.
        """
        # 1. Read current state
        # The executor holds reference to state_manager, will pass it to validate
        # 0. Early return for non-physical commands (set_state, say, etc.)
        kind = getattr(command, 'kind', '') or (command.get('kind', '') if isinstance(command, dict) else '')
        if kind not in ('motion', 'servo'):
             # Pass through action to ESP32 (e.g. set_state) even if not validated by behavior tree
             # This ensures architectural consistency where all actions go through executor
             try:
                 await self.esp32.send_action(command)
             except Exception as e:
                 self.logger.error(f"Error sending non-physical command: {e}")

             # Pass through without modification but marked as safe
             return ValidationResult(is_safe=True, safe_command=command, was_modified=False)

        # 1. Read current safe state Snapshot
        # Use a disconnected snapshot so the behavior rules do not accidentally block 
        # or execute a race condition against heartbeat/thermal background threads.
        current_state = self.state_manager.get_safe_snapshot()
        
        # 2. Query sensors
        # Query sensors from Esp32Client.poll_sensors() (with timeout)
        sensors = {}
        try:
           sensors = await self.esp32.poll_sensors(timeout_s=0.2)
        except Exception as e:
           self.logger.warning(f"Sensor poll failed during safety check: {e}")

        
        # 3. Validate
        result = self.behavior_tree.validate(command, current_state, sensors)
        
        # 4. Execute if safe
        if result.is_safe:
            cmd = result.safe_command
            kind = getattr(cmd, 'kind', 'noop')
            payload = getattr(cmd, 'payload', {}) or {}
            
            try:
                if kind == 'motion':
                     direction = str(payload.get('direction', 'stop'))
                     speed = float(payload.get('speed', 0.0))
                     duration_ms = int(payload.get('duration_ms', 0))
                     motion_cmd = MotionCommand(direction=direction, speed=speed, duration_ms=duration_ms)
                     await self.esp32.send_motion_command(motion_cmd)
                elif kind == 'servo':
                     servo_id = int(payload.get('servo_id', 0))
                     angle = float(payload.get('angle', 0.0))
                     servo_cmd = ServoCommand(servo_id=servo_id, angle=angle)
                     await self.esp32.send_servo_command(servo_id=servo_id, angle=angle)
                elif kind == 'noop':
                     pass
                else:
                     # Generic action fallback
                     await self.esp32.send_action(cmd)
                     
            except Exception as e:
                self.logger.error(f"Error executing safe command: {e}")
        return result

