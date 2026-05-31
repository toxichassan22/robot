import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brain.speech.audio_fsm import AudioFSM
from brain.state.robot_state_manager import RobotStateManager, AudioState, ThermalLevel

from brain.config import BrainConfig
from brain.state.robot_state_manager import RobotMode

def test_audio_fsm_initial_sleep():
    """Verify that AudioFSM starts in SLEEP state and transitions immediately to ACTIVE if pvporcupine is unavailable."""
    cfg = BrainConfig()
    state_manager = RobotStateManager(cfg, initial_mode=RobotMode.IDLE)
    mock_stt = MagicMock()
    mock_audio = MagicMock()
    
    # We force pvporcupine to be unavailable
    with patch('brain.speech.audio_fsm.PORCUPINE_AVAILABLE', False):
        fsm = AudioFSM(
            audio_stream=mock_audio,
            stt=mock_stt,
            state_manager=state_manager,
            wake_word="aria",
            active_timeout_s=5.0
        )
        
        # When pvporcupine is None/unavailable and we call process_audio_chunk in SLEEP state,
        # it should transition immediately to ACTIVE state.
        assert state_manager.get_audio_state() == AudioState.SLEEP
        
        res = fsm.process_audio_chunk(b'\x00' * 100)
        assert res is None
        assert state_manager.get_audio_state() == AudioState.ACTIVE

def test_audio_fsm_thermal_force_sleep():
    """Verify that high thermal levels (HOT/CRITICAL) force AudioFSM to SLEEP and prevent waking up."""
    cfg = BrainConfig()
    state_manager = RobotStateManager(cfg, initial_mode=RobotMode.IDLE)
    mock_stt = MagicMock()
    mock_audio = MagicMock()
    
    with patch('brain.speech.audio_fsm.PORCUPINE_AVAILABLE', False):
        fsm = AudioFSM(
            audio_stream=mock_audio,
            stt=mock_stt,
            state_manager=state_manager,
            wake_word="aria",
            active_timeout_s=5.0
        )
        
        # Move to ACTIVE
        fsm.process_audio_chunk(b'\x00' * 100)
        assert state_manager.get_audio_state() == AudioState.ACTIVE
        
        # Set thermal level to HOT
        state_manager.set_thermal_level(ThermalLevel.HOT)
        
        # Next process_audio_chunk should force state to SLEEP
        res = fsm.process_audio_chunk(b'\x00' * 100)
        assert res is None
        assert state_manager.get_audio_state() == AudioState.SLEEP

def test_audio_fsm_active_timeout():
    """Verify that the ACTIVE state transitions back to SLEEP after inactivity timeout."""
    cfg = BrainConfig()
    state_manager = RobotStateManager(cfg, initial_mode=RobotMode.IDLE)
    mock_stt = MagicMock()
    mock_audio = MagicMock()
    
    with patch('brain.speech.audio_fsm.PORCUPINE_AVAILABLE', False):
        # Set a very short timeout of 0.1 seconds
        fsm = AudioFSM(
            audio_stream=mock_audio,
            stt=mock_stt,
            state_manager=state_manager,
            wake_word="aria",
            active_timeout_s=0.1
        )
        
        # Transition to ACTIVE
        fsm.process_audio_chunk(b'\x00' * 100)
        assert state_manager.get_audio_state() == AudioState.ACTIVE
        
        # Sleep to trigger timeout
        time.sleep(0.15)
        
        # Processing chunk after timeout should return state to SLEEP
        res = fsm.process_audio_chunk(b'\x00' * 100)
        assert res is None
        assert state_manager.get_audio_state() == AudioState.SLEEP

def test_audio_fsm_speech_transcription():
    """Verify that successful STT transcriptions are returned in ACTIVE state."""
    cfg = BrainConfig()
    state_manager = RobotStateManager(cfg, initial_mode=RobotMode.IDLE)
    mock_stt = MagicMock()
    mock_audio = MagicMock()
    
    # Mock STT to return transcription results
    mock_stt.accept_wave.return_value = True
    mock_stt.result.return_value = "مرحبا بك"
    
    with patch('brain.speech.audio_fsm.PORCUPINE_AVAILABLE', False):
        fsm = AudioFSM(
            audio_stream=mock_audio,
            stt=mock_stt,
            state_manager=state_manager,
            wake_word="aria",
            active_timeout_s=5.0
        )
        
        # Transition to ACTIVE
        fsm.process_audio_chunk(b'\x00' * 100)
        
        # Should now transcribe wave and return text
        res = fsm.process_audio_chunk(b'\x00' * 100)
        assert res == "مرحبا بك"
        assert state_manager.get_audio_state() == AudioState.ACTIVE
