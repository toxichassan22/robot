from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any
import threading
import time
from brain.config import BrainConfig # Added import


class RobotMode(Enum):
    NAV = "NAV"
    IDLE = "IDLE"
    EMERGENCY = "EMERGENCY"

class ThermalLevel(Enum):
    NORMAL = "NORMAL"
    WARM = "WARM"
    HOT = "HOT"
    CRITICAL = "CRITICAL"

class VisionLayer(Enum):
    NONE = 0
    MOTION = 1
    OBJECT = 2
    VLM = 3
    ALL = 3

class AudioState(Enum):
    SLEEP = "SLEEP"
    WAKE_WORD = "WAKE_WORD"
    ACTIVE = "ACTIVE"
    PROCESSING = "PROCESSING"

@dataclass
class RobotState:
    mode: RobotMode = RobotMode.IDLE
    thermal_level: ThermalLevel = ThermalLevel.NORMAL
    temp_c: float = 0.0
    vision_layer: VisionLayer = VisionLayer.MOTION
    audio_state: AudioState = AudioState.SLEEP
    speed_limit: float = 0.0
    last_heartbeat_ack_ms: int = 0
    
    # Lock for thread safety
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

class RobotStateManager:
    def __init__(self, config: BrainConfig, initial_mode: RobotMode = RobotMode.IDLE):
        self._state = RobotState(mode=initial_mode)
        self._lock = self._state._lock
        self.config = config
        
        # Initial speed limit based on mode
        self._update_speed_limit()

    def _update_speed_limit(self):
        """Update speed limit based on current mode and thermal level"""
        if self._state.mode in (RobotMode.IDLE, RobotMode.EMERGENCY):
            self._state.speed_limit = 0.0
        elif self._state.mode == RobotMode.NAV:
            # Could be reduced by thermal level
            if self._state.thermal_level == ThermalLevel.CRITICAL:
                 self._state.speed_limit = 0.0
            elif self._state.thermal_level == ThermalLevel.HOT:
                 self._state.speed_limit = (self.config.default_speed_limit * 0.5)
            else:
                 self._state.speed_limit = self.config.default_speed_limit

    def get_mode(self) -> RobotMode:
        with self._lock:
            return self._state.mode

    def set_mode(self, mode: RobotMode) -> bool:
        with self._lock:
            # Validate transitions
            if self._state.mode == RobotMode.EMERGENCY and mode != RobotMode.IDLE:
                 # Can only exit EMERGENCY to IDLE first (manual reset implied)
                 # But for now, let's allow IDLE or NAV if user requests
                 pass
            
            self._state.mode = mode
            self._update_speed_limit()
            return True

    def get_thermal_level(self) -> ThermalLevel:
        with self._lock:
            return self._state.thermal_level
            
    def update_temperature(self, temp_c: float):
        with self._lock:
            self._state.temp_c = temp_c
            
            # Update thermal level logic - simple thresholds
            if temp_c >= self.config.thermal_critical_threshold_c:
                self._state.thermal_level = ThermalLevel.CRITICAL
            elif temp_c >= self.config.thermal_hot_threshold_c:
                self._state.thermal_level = ThermalLevel.HOT
            elif temp_c >= self.config.thermal_warm_threshold_c:
                self._state.thermal_level = ThermalLevel.WARM
            else:
                self._state.thermal_level = ThermalLevel.NORMAL
                
            self._update_speed_limit()

    def set_thermal_level(self, level: ThermalLevel):
        with self._lock:
            self._state.thermal_level = level
            self._update_speed_limit()

    def get_vision_layer(self) -> VisionLayer:
        with self._lock:
            return self._state.vision_layer

    def set_vision_layer(self, layer: VisionLayer):
        with self._lock:
            self._state.vision_layer = layer

    def get_audio_state(self) -> AudioState:
        with self._lock:
            return self._state.audio_state

    def set_audio_state(self, state: AudioState):
        with self._lock:
            self._state.audio_state = state

    def get_speed_limit(self) -> float:
        with self._lock:
            return self._state.speed_limit

    def update_heartbeat_ack(self):
        with self._lock:
            self._state.last_heartbeat_ack_ms = int(time.time() * 1000)

    def get_safe_snapshot(self) -> RobotState:
        """Returns a thread-safe, detached copy of the current state"""
        from dataclasses import replace
        with self._lock:
            return replace(self._state)

    def get_state_dict_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": self._state.mode.value,
                "thermal_level": self._state.thermal_level.value,
                "temp_c": self._state.temp_c,
                "vision_layer": self._state.vision_layer.value,
                "audio_state": self._state.audio_state.value,
                "speed_limit": self._state.speed_limit,
                "last_heartbeat_ack_ms": self._state.last_heartbeat_ack_ms
            }

    def get_state_snapshot(self) -> Dict[str, Any]:
        """
        Backward-compatible snapshot accessor expected by the web layer.

        Returning a dict here keeps callers decoupled from the internal
        dataclass and avoids leaking enum instances across process boundaries.
        """
        return self.get_state_dict_snapshot()
