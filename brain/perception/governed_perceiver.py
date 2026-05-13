import logging
from typing import Any
import time
from brain.perception.perceiver import UnifiedPerceiver
from brain.state.robot_state_manager import RobotStateManager, ThermalLevel, VisionLayer, AudioState
from brain.types import PerceptionState

# Assuming UnifiedPerceiver interface has perceive(text, sensors)
class GovernedPerceiver:
    def __init__(self, perceiver: Any, state_manager: RobotStateManager):
        self.perceiver = perceiver
        self.state_manager = state_manager
        self.logger = logging.getLogger(__name__)

    def start(self):
        self.perceiver.start()

    def stop(self):
        self.perceiver.stop()

    def describe_now(self, prompt: str | None = None, level: int = 2) -> str | None:
        describe = getattr(self.perceiver, "describe_now", None)
        if callable(describe):
            return describe(prompt=prompt, level=level)
        return None

    def snapshot_jpeg(self) -> bytes | None:
        capture = getattr(self.perceiver, "snapshot_jpeg", None)
        if callable(capture):
            return capture()
        return None

    def from_inputs(
        self,
        text: str | None = None,
        vision: dict | None = None,
        sensors: dict | None = None,
        gestures: dict | None = None,
        vision_desc: str | None = None,
    ) -> PerceptionState:
        build = getattr(self.perceiver, "from_inputs", None)
        if callable(build):
            return build(
                text=text,
                vision=vision,
                sensors=sensors,
                gestures=gestures,
                vision_desc=vision_desc,
            )
        return PerceptionState(
            ts_ms=int(time.time() * 1000),
            text=text,
            vision=vision,
            sensors=sensors,
            gestures=gestures,
            vision_desc=vision_desc,
        )

    def _read_runtime_state(self):
        thermal = None
        audio_state = None

        get_snapshot = getattr(self.state_manager, "get_safe_snapshot", None)
        if callable(get_snapshot):
            try:
                snapshot = get_snapshot()
            except Exception:
                snapshot = None
            thermal = getattr(snapshot, "thermal_level", None)
            audio_state = getattr(snapshot, "audio_state", None)

        if not isinstance(thermal, ThermalLevel):
            get_thermal_level = getattr(self.state_manager, "get_thermal_level", None)
            if callable(get_thermal_level):
                thermal = get_thermal_level()

        if not isinstance(audio_state, AudioState):
            get_audio_state = getattr(self.state_manager, "get_audio_state", None)
            if callable(get_audio_state):
                audio_state = get_audio_state()

        if not isinstance(thermal, ThermalLevel):
            thermal = ThermalLevel.CRITICAL
        if not isinstance(audio_state, AudioState):
            audio_state = AudioState.ACTIVE
        return thermal, audio_state

    def _set_frame_skip(self, value: int) -> None:
        cfg = getattr(self.perceiver, "cfg", None)
        if cfg is None:
            return
        try:
            cfg.perf_frame_skip = value
        except Exception:
            pass

    def perceive(
        self,
        text: str | None = None,
        sensors: dict | None = None,
        run_vision: bool | None = None,
        run_gesture: bool | None = None,
        run_vlm: bool | None = None,
    ):
        thermal, audio_state = self._read_runtime_state()
        
        # Map thermal to vision layer
        # CRITICAL=0, HOT=1, WARM=2, NORMAL=3
        layer_map = {
            ThermalLevel.CRITICAL: 0,
            ThermalLevel.HOT: 1,
            ThermalLevel.WARM: 2,
            ThermalLevel.NORMAL: 3
        }
        
        layer_val = layer_map.get(thermal, 0) # Default to 0 (NONE) if unknown
        vision_layer = VisionLayer(layer_val)
        
        # Update state
        self.state_manager.set_vision_layer(vision_layer)
        
        # Determine flags based on layer
        # 0 (NONE): No vision
        # 1 (MOTION): Vision on, Gesture off
        # 2 (OBJECT): Vision on, Gesture on
        # 3 (VLM): Vision on, Gesture on
        
        resolved_run_vision = layer_val >= 1
        resolved_run_gesture = layer_val >= 2
        resolved_run_vlm = layer_val >= 3 # Only NORMAL level enables VLM
        
        # --- ZERO RESOURCE OFFLINE OPTIMIZATION ---
        # Sleep Mode Culling: If robot is not awake, throttle perception drastically 
        # to save CPU/Battery on embedded devices.
        if audio_state == AudioState.SLEEP:
            resolved_run_gesture = False # Disable heavy Mediapipe
            resolved_run_vlm = False     # Disable massive LLM Vision
            self._set_frame_skip(1)
        else:
            self._set_frame_skip(1)

        if run_vision is not None:
            resolved_run_vision = bool(run_vision)
        if run_gesture is not None:
            resolved_run_gesture = bool(run_gesture)
        if run_vlm is not None:
            resolved_run_vlm = bool(run_vlm)

        return self.perceiver.perceive(
            text=text, 
            sensors=sensors, 
            run_vision=resolved_run_vision, 
            run_gesture=resolved_run_gesture,
            run_vlm=resolved_run_vlm
        )

