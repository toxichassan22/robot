import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brain.types import ActionCommand
from brain.state.robot_state_manager import RobotState, RobotMode, ThermalLevel
from brain.state.types import ValidationResult
from brain.cognition.safe_executor import SafeCommandExecutor
from brain.cognition.safety.behavior_tree import BehaviorTree
from brain.cognition.safety.rules import ModeCheckRule, SpeedLimitRule, ObstacleRule, ThermalRule

def test_mode_check_rule():
    """Verify that ModeCheckRule blocks motion commands when robot is IDLE."""
    rule = ModeCheckRule()
    state = RobotState(mode=RobotMode.IDLE, speed_limit=1.0, thermal_level=ThermalLevel.NORMAL)
    cmd = ActionCommand(kind="motion", payload={"direction": "forward", "speed": 0.8})
    
    result = rule.validate(cmd, state, {})
    assert result.is_safe is False
    assert result.safe_command.kind == "noop"
    assert "locked" in result.reason

def test_speed_limit_rule():
    """Verify that SpeedLimitRule caps speed at state's configured limit."""
    rule = SpeedLimitRule()
    state = RobotState(mode=RobotMode.NAV, speed_limit=0.5, thermal_level=ThermalLevel.NORMAL)
    cmd = ActionCommand(kind="motion", payload={"direction": "forward", "speed": 0.8})
    
    result = rule.validate(cmd, state, {})
    assert result.is_safe is True
    assert result.was_modified is True
    assert result.safe_command.payload["speed"] == 0.5
    assert "Speed limited to" in result.reason

def test_obstacle_rule():
    """Verify that ObstacleRule halts motion under 10cm, and reduces speed under 20cm."""
    rule = ObstacleRule()
    state = RobotState(mode=RobotMode.NAV, speed_limit=1.0, thermal_level=ThermalLevel.NORMAL)
    cmd = ActionCommand(kind="motion", payload={"direction": "forward", "speed": 0.8})
    
    # Under 10cm - Obstacle halt
    result = rule.validate(cmd, state, {"obstacle_distance_cm": 5.0})
    assert result.is_safe is False
    assert result.safe_command.kind == "noop"
    assert "Obstacle detected" in result.reason
    
    # Under 20cm - Speed reduction
    result = rule.validate(cmd, state, {"obstacle_distance_cm": 15.0})
    assert result.is_safe is True
    assert result.was_modified is True
    assert result.safe_command.payload["speed"] == 0.2

def test_thermal_rule():
    """Verify that ThermalRule throttles speed on HOT CPU and blocks servos on CRITICAL."""
    rule = ThermalRule()
    
    # Case 1: HOT thermal limits speed to 0.3
    state_hot = RobotState(mode=RobotMode.NAV, speed_limit=1.0, thermal_level=ThermalLevel.HOT)
    cmd_motion = ActionCommand(kind="motion", payload={"direction": "forward", "speed": 0.8})
    result_motion = rule.validate(cmd_motion, state_hot, {})
    assert result_motion.is_safe is True
    assert result_motion.safe_command.payload["speed"] == 0.3
    
    # Case 2: CRITICAL thermal blocks servo
    state_critical = RobotState(mode=RobotMode.NAV, speed_limit=1.0, thermal_level=ThermalLevel.CRITICAL)
    cmd_servo = ActionCommand(kind="servo", payload={"servo_id": 1, "angle": 90})
    result_servo = rule.validate(cmd_servo, state_critical, {})
    assert result_servo.is_safe is False
    assert result_servo.safe_command.kind == "noop"

@pytest.mark.anyio
async def test_safe_executor_flow():
    """Verify that SafeCommandExecutor chain evaluates rules and interacts with ESP32."""
    esp32_mock = AsyncMock()
    esp32_mock.poll_sensors.return_value = {"obstacle_distance_cm": 15.0}
    
    # Set up RobotStateManager mock
    state_mock = MagicMock()
    state_mock.get_safe_snapshot.return_value = RobotState(
        mode=RobotMode.NAV, speed_limit=0.5, thermal_level=ThermalLevel.NORMAL
    )
    
    # Assemble rules into behavior tree
    behavior_tree = BehaviorTree(rules=[SpeedLimitRule(), ObstacleRule()])
    executor = SafeCommandExecutor(esp32_mock, state_mock, behavior_tree)
    
    # Test execution of action that hits both SpeedLimit and Obstacle rules
    cmd = ActionCommand(kind="motion", payload={"direction": "forward", "speed": 0.9})
    
    result = await executor.execute(cmd)
    
    # Speed is limited by SpeedLimit (0.5), then further capped by Obstacle (0.2)
    assert result.is_safe is True
    assert result.was_modified is True
    assert result.safe_command.payload["speed"] == 0.2
    
    # Ensure ESP32 send_motion_command was called with modified values
    esp32_mock.send_motion_command.assert_called_once()
    motion_arg = esp32_mock.send_motion_command.call_args[0][0]
    assert motion_arg.direction == "forward"
    assert motion_arg.speed == 0.2
