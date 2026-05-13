import unittest
from unittest.mock import MagicMock, patch, ANY
import time
import os
import sys

# Ensure we can import from brain
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Pre-mock pvporcupine to avoid top-level import errors or dependency on actual hardware
mock_pv = MagicMock()
sys.modules['pvporcupine'] = mock_pv

from brain.perception.governed_perceiver import GovernedPerceiver
from brain.speech.audio_fsm import AudioFSM
from brain.state.robot_state_manager import RobotStateManager, ThermalLevel, VisionLayer, AudioState

class TestVerificationUpdates(unittest.TestCase):
    
    def test_governed_perceiver_thermal_logic(self):
        """Test that perception layer is set according to thermal level."""
        mock_perceiver = MagicMock()
        mock_state_manager = MagicMock()
        
        governed = GovernedPerceiver(mock_perceiver, mock_state_manager)
        
        cases = [
            (ThermalLevel.NORMAL, 3),   # Vision + Gesture + VLM
            (ThermalLevel.WARM, 2),     # Vision + Gesture
            (ThermalLevel.HOT, 1),      # Vision only
            (ThermalLevel.CRITICAL, 0), # None
        ]

        for thermal_level, expected_val in cases:
            with self.subTest(thermal=thermal_level):
                mock_state_manager.get_thermal_level.return_value = thermal_level
                
                governed.perceive(text="test")
                
                # Check vision layer set
                # Note: valid call is set_vision_layer(VisionLayer(expected_val))
                # verify the value passed
                args, _ = mock_state_manager.set_vision_layer.call_args
                self.assertEqual(args[0].value, expected_val)
                
                # Check flags propagated to perceiver
                expected_run_vision = expected_val >= 1
                expected_run_gesture = expected_val >= 2
                expected_run_vlm = expected_val >= 3
                
                mock_perceiver.perceive.assert_called_with(
                    text="test",
                    sensors=None,
                    run_vision=expected_run_vision,
                    run_gesture=expected_run_gesture,
                    run_vlm=expected_run_vlm
                )

    @patch('brain.speech.audio_fsm.pvporcupine')
    @patch('brain.speech.audio_fsm.PORCUPINE_AVAILABLE', True)
    def test_audio_fsm_wakeword_and_timeout(self, mock_porcupine):
        """Test simple wakeword detection and timeout."""
        mock_stream = MagicMock()
        mock_stt = MagicMock()
        mock_state_manager = MagicMock()
        
        # Setup Porcupine Mock
        mock_pp_instance = MagicMock()
        mock_porcupine.create.return_value = mock_pp_instance
        mock_pp_instance.frame_length = 512
        mock_pp_instance.process.return_value = -1 # No detect
        
        # Setup State Manager
        mock_state_manager.get_audio_state.return_value = AudioState.SLEEP
        mock_state_manager.get_thermal_level.return_value = ThermalLevel.NORMAL
        
        # Create FSM
        fsm = AudioFSM(
            audio_stream=mock_stream,
            stt=mock_stt,
            state_manager=mock_state_manager,
            wake_word="test",
            active_timeout_s=1.0
        )
        
        # Init verification
        mock_state_manager.set_audio_state.assert_called_with(AudioState.SLEEP)
        
        # --- Test Wakeword ---
        # Chunk size needed: 512 * 2 bytes = 1024
        chunk = b'\x00' * 1024
        
        # 1. No detect
        fsm.process_audio_chunk(chunk)
        # Verify NO transition to active. Last call should be Sleep (from init) or no new call.
        # We can check the number of calls to set_audio_state
        self.assertEqual(mock_state_manager.set_audio_state.call_count, 1) # Just the init ONE
        
        # 2. Detect
        mock_pp_instance.process.return_value = 0 # Detected
        fsm.process_audio_chunk(chunk)
        
        # Verify transition to Active
        mock_state_manager.set_audio_state.assert_called_with(AudioState.ACTIVE)
        
        # --- Test Timeout ---
        # Update mock state to be active
        mock_state_manager.get_audio_state.return_value = AudioState.ACTIVE
        
        with patch('time.time') as mock_time:
            # We must set start time relative to what we want
            # FSM sets last_activity = ts on wake
            # Let's say wakeup happened at T=100
            fsm.last_activity = 100.0
            
            # Case A: Within timeout (T=100.5)
            mock_time.return_value = 100.5
            fsm.process_audio_chunk(chunk)
            
            # Verify NOT set to sleep. Last call was ACTIVE.
            self.assertEqual(mock_state_manager.set_audio_state.call_args[0][0], AudioState.ACTIVE)
            
            # Case B: Timeout (T=102.0) > 1.0s limit
            mock_time.return_value = 102.0
            fsm.process_audio_chunk(chunk)
            
            # Verify set to sleep
            self.assertEqual(mock_state_manager.set_audio_state.call_args[0][0], AudioState.SLEEP)

if __name__ == "__main__":
    unittest.main()
