import time
import logging
import struct
from typing import Any, Optional
from brain.state.robot_state_manager import RobotStateManager, AudioState, ThermalLevel

try:
    import pvporcupine
    PORCUPINE_AVAILABLE = True
except Exception as e:
    # Catching generic Exception because pvporcupine might raise RuntimeError 
    # if resources are missing even if installed.
    pvporcupine = None
    logging.warning(f"pvporcupine not found or failed to load: {e}")
    PORCUPINE_AVAILABLE = False

class AudioFSM:
    def __init__(
        self, 
        audio_stream: Any, 
        stt: Any, 
        state_manager: RobotStateManager, 
        wake_word: str, 
        active_timeout_s: float = 30.0,
        require_wakeword: bool = False
    ):
        self.audio = audio_stream
        self.stt = stt
        self.state_manager = state_manager
        self.wake_word = wake_word.lower()
        self.active_timeout_s = active_timeout_s
        
        self.last_activity = 0.0
        self.logger = logging.getLogger(__name__)
        
        # Porcupine initialization
        self.porcupine = None
        self._audio_buffer = []
        
        if PORCUPINE_AVAILABLE:
            try:
                kw = self.wake_word if getattr(pvporcupine, 'KEYWORDS', None) and self.wake_word in pvporcupine.KEYWORDS else 'picovoice'
                if kw != self.wake_word:
                    self.logger.warning(f"Wake word '{self.wake_word}' not builtin. Using '{kw}'")
                
                self.porcupine = pvporcupine.create(keywords=[kw])
                self.logger.info(f"Porcupine initialized with keyword '{kw}'")
            except Exception as e:
                self.logger.error(f"Failed to initialize Porcupine: {e}")
                self.porcupine = None
        
        if self.porcupine is None:
            if require_wakeword:
                 raise RuntimeError("Wakeword required but Porcupine unavailable/failed.")
            else:
                 self.logger.warning("Wakeword disabled (unavailable). Audio will retain SLEEP until manual ACTIVE or always open depending on configuration.")
        
        # Initial state
        self._transition_to(AudioState.SLEEP)

    def _transition_to(self, state: AudioState):
        self.state_manager.set_audio_state(state)
        self.logger.info(f"AudioFSM -> {state.value}") 

    def process_audio_chunk(self, chunk: bytes) -> Optional[str]:
        current_state = self.state_manager.get_audio_state()
        thermal = self.state_manager.get_thermal_level()
        
        # Thermal Force Sleep
        if thermal in (ThermalLevel.HOT, ThermalLevel.CRITICAL):
            if current_state != AudioState.SLEEP:
                self.logger.warning("Forcing Audio SLEEP due to thermal load")
                self._transition_to(AudioState.SLEEP)
            # Ensure buffer doesn't grow indefinitely in sleep
            self._audio_buffer = [] 
            return None # Skip processing

        ts = time.time()
        
        # --- Wakeword Processing (SLEEP state) ---
        if current_state == AudioState.SLEEP:
            if not self.porcupine:
                 # Wakeword disabled/unavailable -> Treat as always listening or immediately active
                 # However, we don't want to spam ACTIVE if we just timed out.
                 # Actually, if we timed out to SLEEP, and have no wakeword, how do we wake up?
                 # If we have no wakeword, we are effectively "Always Open" (Push-to-talk logic effectively, but here automatic?)
                 # The user instruction: "when self.porcupine is None, transition to AudioState.ACTIVE and route chunks to stt.accept_wave() so STT still functions, and log that wakeword detection is disabled."
                 
                 # We should probably do this transition ONCE or when we have data.
                 # If we transition here, we return None for this chunk, but next chunk will be processed in ACTIVE block.
                 if self.state_manager.get_audio_state() == AudioState.SLEEP:
                    self.logger.warning("Wakeword disabled. Transitioning to ACTIVE immediately.")
                    self._transition_to(AudioState.ACTIVE)
                    self.last_activity = ts
                 return None

            # Buffer management for Porcupine (requires fixed frame size)
            # chunk is bytes (int16) -> unpack to shorts
            count = len(chunk) // 2
            shorts = struct.unpack(f'{count}h', chunk)
            self._audio_buffer.extend(shorts)
            
            while len(self._audio_buffer) >= self.porcupine.frame_length:
                frame = self._audio_buffer[:self.porcupine.frame_length]
                self._audio_buffer = self._audio_buffer[self.porcupine.frame_length:]
                
                result = self.porcupine.process(frame)
                if result >= 0:
                    self.logger.info("Wakeword DETECTED!")
                    self.last_activity = ts
                    self._transition_to(AudioState.ACTIVE)
                    # Clear buffer on wake
                    self._audio_buffer = []
                    return None 

        # --- Active Command Processing (ACTIVE state) ---
        elif current_state == AudioState.ACTIVE:
            # Check Timeout
            if ts - self.last_activity > self.active_timeout_s:
                self.logger.info("Audio FSM timeout -> SLEEP")
                self._transition_to(AudioState.SLEEP)
                return None

            # Feed to STT
            if self.stt.accept_wave(chunk):
                text = self.stt.result()
                if text:
                    self.logger.info(f"STT Heard: '{text}'")
                    self.last_activity = ts
                    return text
            
        return None
