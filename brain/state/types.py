from dataclasses import dataclass, field, asdict
from typing import Optional, Any
import json
import time

@dataclass
class HeartbeatPayload:
    mode: str
    speed_limit: float
    temp_c: float
    timestamp_ms: int

    def to_json(self) -> dict:
        return asdict(self)

@dataclass
class ValidationResult:
    is_safe: bool
    safe_command: Any  # ActionCommand
    was_modified: bool = False
    reason: str = ""
