import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import asdict

from brain.runtime import BrainRuntime
from brain.config import BrainConfig
from brain.types import PerceptionState, ActionCommand
from brain.state.robot_state_manager import RobotStateManager, ThermalLevel, VisionLayer, AudioState
from brain.perception.governed_perceiver import GovernedPerceiver

class TestRuntimeIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cfg = BrainConfig()
        self.mock_transport = MagicMock()
        
        # Patch heavily to avoid starting real threads/processes
        with patch('brain.runtime._load_robot_settings', return_value={}), \
             patch('brain.runtime.SqliteMemory'), \
             patch('brain.runtime.Esp32Client'), \
             patch('brain.runtime.UnifiedPerceiver'), \
             patch('brain.perception.governed_perceiver.UnifiedPerceiver'), \
             patch('brain.runtime.AudioStream'), \
             patch('brain.runtime.VoskSTT'), \
             patch('brain.runtime.build_tts'), \
             patch('brain.runtime.MotionPlanner'):
            
            self.runtime = BrainRuntime(self.cfg, self.mock_transport)
            
        # Replace safe_executor with MagicMock to control execute results
        self.runtime.safe_executor = AsyncMock()
        # Mock planner
        self.runtime.planner = AsyncMock()
        
    async def test_governed_perceiver_thermal_layers(self):
        # Setup
        mock_perceiver = MagicMock()
        mock_state_manager = MagicMock()
        
        gp = GovernedPerceiver(mock_perceiver, mock_state_manager)
        
        # Test Case 1: CRITICAL Thermal -> No Vision
        mock_state_manager.get_thermal_level.return_value = ThermalLevel.CRITICAL
        gp.perceive(text="foo")
        
        mock_state_manager.set_vision_layer.assert_called_with(VisionLayer.NONE)
        mock_perceiver.perceive.assert_called_with(
            text="foo", sensors=None, run_vision=False, run_gesture=False, run_vlm=False
        )
        
        # Test Case 2: WARM Thermal -> Vision + Gesture, No VLM?
        # Map: CRITICAL=NONE, HOT=MOTION(1), WARM=OBJECT(2), NORMAL=ALL(3)
        mock_state_manager.get_thermal_level.return_value = ThermalLevel.WARM
        gp.perceive(text="foo")
        
        mock_state_manager.set_vision_layer.assert_called_with(VisionLayer.OBJECT)
        mock_perceiver.perceive.assert_called_with(
            text="foo", sensors=None, run_vision=True, run_gesture=True, run_vlm=False
        )
        
        # Test Case 3: HOT Thermal -> Motion only
        mock_state_manager.get_thermal_level.return_value = ThermalLevel.HOT
        gp.perceive(text="foo")
        
        mock_state_manager.set_vision_layer.assert_called_with(VisionLayer.MOTION)
        mock_perceiver.perceive.assert_called_with(
            text="foo", sensors=None, run_vision=True, run_gesture=False, run_vlm=False
        )
        
        # Test Case 4: NORMAL Thermal -> All
        mock_state_manager.get_thermal_level.return_value = ThermalLevel.NORMAL
        gp.perceive(text="foo")
        
        mock_state_manager.set_vision_layer.assert_called_with(VisionLayer.ALL)
        mock_perceiver.perceive.assert_called_with(
            text="foo", sensors=None, run_vision=True, run_gesture=True, run_vlm=True
        )
        
    async def test_handle_perception_updates_state_on_set_state(self):
        # Prepare a decision that returns a set_state action
        # Mock gate to return immediate action
        self.runtime.gate = MagicMock()
        decision_mock = MagicMock()
        decision_mock.immediate_action = ActionCommand(kind="set_state", payload={"mode": "awake"})
        decision_mock.should_plan = False
        decision_mock.rewritten_text = None
        self.runtime.gate.on_perception.return_value = decision_mock
        
        # Mock safe executor to return safe result
        from brain.state.types import ValidationResult
        self.runtime.safe_executor.execute.return_value = ValidationResult(
            is_safe=True, 
            safe_command=decision_mock.immediate_action, 
            was_modified=False
        )

        perception = PerceptionState(ts_ms=100, text="aria wake up")
        
        # Mock state_manager
        self.runtime.state_manager = MagicMock()
        
        # Mock TTS callback
        mock_tts = AsyncMock()
        
        await self.runtime.handle_perception(perception, tts_callback=mock_tts)
        
        # Verify state manager update
        self.runtime.state_manager.set_audio_state.assert_called_with(AudioState.ACTIVE)
        
        # Verify that gate.is_awake was set to True
        # Since we mocked self.runtime.gate, we check if the attribute was set on the mock
        self.assertEqual(self.runtime.gate.is_awake, True)

        # Verify TTS callback - should say "نعم؟" for wake up
        mock_tts.assert_called_with("نعم؟")

    async def test_handle_perception_safety_override(self):
        # Mock gate to return an action
        self.runtime.gate = MagicMock()
        decision_mock = MagicMock()
        decision_mock.immediate_action = ActionCommand(kind="motion", payload={"speed": 100})
        decision_mock.should_plan = False
        decision_mock.rewritten_text = None
        self.runtime.gate.on_perception.return_value = decision_mock
        
        # Mock safe executor to return MODIFIED result
        from brain.state.types import ValidationResult
        safe_cmd = ActionCommand(kind="motion", payload={"speed": 50})
        self.runtime.safe_executor.execute.return_value = ValidationResult(
            is_safe=True, 
            safe_command=safe_cmd, 
            was_modified=True,
            reason="Speed limit"
        )
        
        # Mock _log_safety_event
        self.runtime._log_safety_event = AsyncMock()
        
        perception = PerceptionState(ts_ms=100, text="go fast")
        
        await self.runtime.handle_perception(perception, print_events=False)
        
        self.runtime._log_safety_event.assert_called_once()
        args = self.runtime._log_safety_event.call_args[1]
        self.assertEqual(args['event_type'], "command_override")
        self.assertEqual(args['reason'], "Speed limit")

    async def test_voice_loop_integration_with_audio_fsm(self):
        # Verify voice loop reads from FSM and calls handle_perception
        
        # Setup mocks
        self.runtime.audio = MagicMock()
        self.runtime.audio.read.side_effect = [b'chunk', asyncio.CancelledError] # Read one chunk then stop
        self.runtime.audio_fsm = MagicMock()
        
        # FSM returns text on first chunk
        self.runtime.audio_fsm.process_audio_chunk.return_value = "hello robot"
        
        self.runtime.handle_perception = AsyncMock()
        self.runtime.tts = MagicMock()
        self.runtime.gate = MagicMock()
        self.runtime.gate.is_awake = False
        
        self.runtime.state_manager = MagicMock()
        self.runtime.state_manager.get_audio_state.return_value = AudioState.SLEEP 
        
        try:
            await self.runtime.voice_loop()
        except asyncio.CancelledError:
            pass
            
        # Verify interactions
        self.runtime.audio_fsm.process_audio_chunk.assert_called_with(b'chunk')
        
        # Should have synced gate and state
        self.assertTrue(self.runtime.gate.is_awake)
        self.runtime.state_manager.set_audio_state.assert_called_with(AudioState.ACTIVE)
        
        # Should have called handle_perception
        self.runtime.handle_perception.assert_called_once()
        args = self.runtime.handle_perception.call_args[0]
        perception = args[0]
        self.assertEqual(perception.text, "hello robot")
