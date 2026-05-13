import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from brain.speech.audio_fsm import AudioFSM
from brain.state.robot_state_manager import RobotStateManager, AudioState, ThermalLevel

class TestAudioFSM(unittest.TestCase):
    def setUp(self):
        self.mock_audio = MagicMock()
        self.mock_stt = MagicMock()
        self.mock_state_manager = MagicMock()
        self.mock_state_manager.get_audio_state.return_value = AudioState.SLEEP
        self.mock_state_manager.get_thermal_level.return_value = ThermalLevel.NORMAL
        
        # Patch pvporcupine in audio_fsm if needed, or just mock self.porcupine in instance
        # We will mock the porcupine instance inside FSM
        
    def test_wakeword_transition(self):
        # Initialize FSM
        fsm = AudioFSM(self.mock_audio, self.mock_stt, self.mock_state_manager, wake_word="computer")
        
        # Inject mock porcupine
        mock_porcupine = MagicMock()
        mock_porcupine.frame_length = 5
        mock_porcupine.process.return_value = -1 # No wake word yet
        fsm.porcupine = mock_porcupine
        fsm.frame_length = 5
        
        # 1. Feed audio, no wake
        fsm.process_audio_chunk(b'\x00' * 10) # 10 bytes = 5 samples * 2 bytes
        # Should call process
        mock_porcupine.process.assert_called()
        self.mock_state_manager.set_audio_state.assert_called_with(AudioState.SLEEP) # Initial
        
        # 2. Feed audio, WAKE detected
        mock_porcupine.process.return_value = 0 # Detected
        fsm.process_audio_chunk(b'\x00' * 10)
        
        # Verify transition to ACTIVE
        self.mock_state_manager.set_audio_state.assert_called_with(AudioState.ACTIVE)
        
    def test_thermal_force_sleep(self):
        fsm = AudioFSM(self.mock_audio, self.mock_stt, self.mock_state_manager, wake_word="computer")
        self.mock_state_manager.get_audio_state.return_value = AudioState.ACTIVE
        self.mock_state_manager.get_thermal_level.return_value = ThermalLevel.HOT
        
        fsm.process_audio_chunk(b'some audio')
        
        # Should force sleep
        self.mock_state_manager.set_audio_state.assert_called_with(AudioState.SLEEP)

    def test_stt_fallback(self):
        # FSM without porcupine
        fsm = AudioFSM(self.mock_audio, self.mock_stt, self.mock_state_manager, wake_word="computer")
        fsm.porcupine = None
        
        self.mock_stt.accept_wave.return_value = True
        self.mock_stt.result.return_value = "hello computer please wake up"
        
        result = fsm.process_audio_chunk(b'audio')
        
        # Should detect wake word via text and return text
        self.mock_state_manager.set_audio_state.assert_called_with(AudioState.ACTIVE)
        self.assertEqual(result, "hello computer please wake up")

if __name__ == '__main__':
    unittest.main()
