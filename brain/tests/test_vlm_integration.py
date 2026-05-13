import logging
import time
from unittest.mock import MagicMock, patch
# Mock cv2 to avoid dependency issues in test env
import sys
from unittest.mock import MagicMock, patch

mock_cv2 = MagicMock()
# cv2.imencode returns (ret, buffer), where buffer is numpy array.
# We mock the buffer to have tobytes() method.
mock_buffer = MagicMock()
mock_buffer.tobytes.return_value = b'fake_jpg_bytes'
mock_cv2.imencode.return_value = (True, mock_buffer)
mock_cv2.cvtColor.return_value = "gray"
sys.modules["cv2"] = mock_cv2

# Mock mediapipe to avoid import errors in GestureDetector
mock_mp = MagicMock()
sys.modules["mediapipe"] = mock_mp

import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Now import brain modules
from brain.config import BrainConfig
from brain.state.robot_state_manager import RobotStateManager, ThermalLevel
from brain.perception.governed_perceiver import GovernedPerceiver
from brain.perception.perceiver import UnifiedPerceiver
from brain.types import PerceptionState

def test_vlm_flow():
    logging.basicConfig(level=logging.INFO)
    print("Testing VLM Integration Flow...")
    
    cfg = BrainConfig.from_env()
    state_manager = RobotStateManager(cfg)
    
    # Mock VLMClient
    with patch("brain.perception.perceiver.VLMClient") as MockVLM:
        mock_vlm_instance = MockVLM.return_value
        mock_vlm_instance.analyze_image.return_value = "A robot performing a test"
        
        # Mock Camera
        with patch("brain.perception.perceiver.Camera") as MockCamera:
            mock_cam = MockCamera.return_value
            mock_cam.get_latest_frame.return_value = "dummy_frame"
            
            perceiver = UnifiedPerceiver(cfg)
            # Inject mocks into perceiver manually if needed, or rely on UnifiedPerceiver instantiating them
            # UnifiedPerceiver instantiates Camera on init. 
            # But we patched the class, so self.camera is the mock.
            # It also instantiates self.vlm.
            
            governed = GovernedPerceiver(perceiver, state_manager)
            
            # --- Test 1: CRITICAL Thermal ---
            print("\n[Test 1] Thermal Level: CRITICAL")
            state_manager.set_thermal_level(ThermalLevel.CRITICAL)
            p_crit = governed.perceive()
            
            if p_crit.vision_desc is None:
                print("PASS: Vision description is None (as expected for CRITICAL).")
            else:
                print(f"FAIL: Vision description is present: {p_crit.vision_desc}")
            
            # --- Test 2: NORMAL Thermal ---
            print("\n[Test 2] Thermal Level: NORMAL")
            state_manager.set_thermal_level(ThermalLevel.NORMAL)
            
            # The rate limit check in perceiver is: time.time() - self.last_vlm_ts > 5.0
            # initialized to 0.0. Current time is large. Should run.
            p_norm = governed.perceive()
            
            if p_norm.vision_desc == "A robot performing a test":
                print("PASS: Vision description received from VLM.")
            else:
                print(f"FAIL: Expected description, got: {p_norm.vision_desc}")
                # Debug why
                if not governed.perceiver.camera:
                   print("Debug: Camera is None")

if __name__ == "__main__":
    test_vlm_flow()
