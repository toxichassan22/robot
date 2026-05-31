import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brain.config import BrainConfig

def test_brain_config_default_values():
    """Verify that BrainConfig is initialized with correct defaults."""
    cfg = BrainConfig()
    assert cfg.log_level == "INFO"
    assert cfg.transport == "mock"
    assert cfg.esp32_tcp_host == "127.0.0.1"
    assert cfg.esp32_tcp_port == 8765
    assert cfg.wake_word == "aria"
    assert cfg.sleep_timeout_s == 20.0

def test_brain_config_parse_helpers():
    """Verify that BrainConfig helper methods parse types and boundaries correctly."""
    # Test _parse_int helper
    os.environ["TEST_INT_VAL"] = "45"
    assert BrainConfig._parse_int("TEST_INT_VAL", 10) == 45
    
    os.environ["TEST_INT_VAL"] = "invalid"
    assert BrainConfig._parse_int("TEST_INT_VAL", 10) == 10
    
    # Test boundaries
    os.environ["TEST_INT_BOUNDS"] = "200"
    assert BrainConfig._parse_int("TEST_INT_BOUNDS", 50, min_v=10, max_v=100) == 50

    # Test _parse_float helper
    os.environ["TEST_FLOAT_VAL"] = "3.14"
    assert BrainConfig._parse_float("TEST_FLOAT_VAL", 1.0) == 3.14

def test_brain_config_validate_http_url():
    """Verify that _validate_http_url validates schemes and cleans trailing slashes."""
    assert BrainConfig._validate_http_url("TEST_NONEXISTENT", "http://default.com") == "http://default.com"
    
    os.environ["TEST_URL"] = "https://my-robot.local/"
    assert BrainConfig._validate_http_url("TEST_URL", "http://default.com") == "https://my-robot.local"

    os.environ["TEST_URL"] = "ftp://invalid-scheme.com"
    assert BrainConfig._validate_http_url("TEST_URL", "http://default.com") == "http://default.com"

def test_brain_config_with_ollama_model():
    """Verify with_ollama_model returns a new config copy with changed model."""
    cfg = BrainConfig()
    new_cfg = cfg.with_ollama_model("qwen3.5")
    assert cfg.ollama_model == ""
    assert new_cfg.ollama_model == "qwen3.5"
    assert new_cfg is not cfg  # Frozen dataclass returns a copy
