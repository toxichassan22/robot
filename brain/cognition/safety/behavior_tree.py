from abc import ABC, abstractmethod
from typing import List, Dict, Any
from brain.state.types import ValidationResult
from brain.state.robot_state_manager import RobotState

# Assuming ActionCommand matches the structure used in the planner
# I'll define a dummy or import if I can find it.
# The plan mentions `ActionCommand` in `validate`.
# I'll type hint as Any for now to avoid circular imports if ActionCommand is deep,
# but ideally it should be imported.
# Let's check `brain/cognition/planning.py` or similar later.
# For now, Any is safe.

class SafetyRule(ABC):
    @abstractmethod
    def validate(self, command: Any, state: RobotState, sensors: Dict[str, Any]) -> ValidationResult:
        """
        Validate a command against this rule.
        Returns a ValidationResult indicating success, failure, or modification.
        """
        pass

class BehaviorTree:
    def __init__(self, rules: List[SafetyRule]):
        self.rules = rules

    def validate(self, command: Any, state: RobotState, sensors: Dict[str, Any]) -> ValidationResult:
        """
        Run the command through all safety rules.
        """
        current_command = command
        modified = False
        
        for rule in self.rules:
            result = rule.validate(current_command, state, sensors)
            
            if not result.is_safe:
                # If any rule blocks the command, return immediately
                return result
            
            if result.was_modified:
                # If command was modified (e.g. speed limited), use the new command for subsequent rules
                current_command = result.safe_command
                modified = True
                
        # If all passed
        return ValidationResult(
            is_safe=True, 
            safe_command=current_command, 
            was_modified=modified,
            reason="All safety checks passed" if not modified else "Command modified by safety rules"
        )
