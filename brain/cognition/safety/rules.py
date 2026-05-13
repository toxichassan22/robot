from typing import Dict, Any
from dataclasses import replace
from .behavior_tree import SafetyRule
from brain.state.types import ValidationResult
from brain.state.robot_state_manager import RobotState, RobotMode, ThermalLevel

class ModeCheckRule(SafetyRule):
    def validate(self, command: Any, state: RobotState, sensors: Dict[str, Any]) -> ValidationResult:
        kind = getattr(command, 'kind', '')
        if kind == 'motion':
            if state.mode in (RobotMode.IDLE, RobotMode.EMERGENCY):
                noop_command = replace(command, kind="noop")
                return ValidationResult(
                    is_safe=False,
                    safe_command=noop_command,
                    was_modified=True,
                    reason=f"Motors locked in {state.mode.value} mode"
                )
        return ValidationResult(is_safe=True, safe_command=command)

class SpeedLimitRule(SafetyRule):
    def validate(self, command: Any, state: RobotState, sensors: Dict[str, Any]) -> ValidationResult:
        if getattr(command, 'kind', '') == 'motion':
            # Assuming payload has 'speed'
            payload = getattr(command, 'payload', {})
            speed = payload.get('speed', 0.0)
            
            if speed > state.speed_limit:
                new_payload = payload.copy()
                new_payload['speed'] = state.speed_limit
                new_command = replace(command, payload=new_payload)
                
                return ValidationResult(
                    is_safe=True,
                    safe_command=new_command,
                    was_modified=True,
                    reason=f"Speed limited to {state.speed_limit}"
                )
        return ValidationResult(is_safe=True, safe_command=command)

class ObstacleRule(SafetyRule):
    def validate(self, command: Any, state: RobotState, sensors: Dict[str, Any]) -> ValidationResult:
        if getattr(command, 'kind', '') == 'motion':
            distance = sensors.get("obstacle_distance_cm", 999.0)
            payload = getattr(command, 'payload', {})
            speed = payload.get('speed', 0.0)
            
            if speed > 0:
                if distance < 10.0:
                    noop_command = replace(command, kind="noop")
                    return ValidationResult(
                        is_safe=False,
                        safe_command=noop_command, 
                        was_modified=True,
                        reason="Obstacle detected (<10cm)"
                    )
                elif distance < 20.0:
                    if speed > 0.2:
                        new_payload = payload.copy()
                        new_payload['speed'] = 0.2
                        new_command = replace(command, payload=new_payload)
                        return ValidationResult(
                            is_safe=True, 
                            safe_command=new_command,
                            was_modified=True,
                            reason="Obstacle near (<20cm), speed reduced"
                        )
        return ValidationResult(is_safe=True, safe_command=command)

class ThermalRule(SafetyRule):
    def validate(self, command: Any, state: RobotState, sensors: Dict[str, Any]) -> ValidationResult:
        if state.thermal_level in (ThermalLevel.HOT, ThermalLevel.CRITICAL):
            kind = getattr(command, 'kind', '')
            if kind == 'motion':
                payload = getattr(command, 'payload', {})
                speed = payload.get('speed', 0.0)
                
                if speed > 0.5:
                    new_payload = payload.copy()
                    new_payload['speed'] = 0.3
                    new_command = replace(command, payload=new_payload)
                    return ValidationResult(
                        is_safe=True,
                        safe_command=new_command,
                        was_modified=True,
                        reason="Thermal throttling active (Hot/Critical)"
                    )
            elif kind == 'servo':
                 # Block servo in critical
                 if state.thermal_level == ThermalLevel.CRITICAL:
                    noop_command = replace(command, kind="noop")
                    return ValidationResult(
                        is_safe=False,
                        safe_command=noop_command,
                        was_modified=True,
                        reason="Servo disabled in Critical thermal state"
                    )
            
        return ValidationResult(is_safe=True, safe_command=command)

