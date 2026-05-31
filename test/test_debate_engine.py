import sys
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from brain.debate_engine import DebateEngine

def test_debate_engine_initialization():
    """Verify that DebateEngine initializes with custom configurations."""
    mock_model = MagicMock()
    mock_model.name = "Kimi"
    
    custom_search_settings = {
        "max_queries_per_model": 5,
        "enable_round_0": False
    }
    
    engine = DebateEngine(
        models=[mock_model],
        search_settings=custom_search_settings
    )
    
    assert engine.models == [mock_model]
    assert engine.rounds == 5
    assert engine.search_settings["max_queries_per_model"] == 5
    assert engine.search_settings["enable_round_0"] is False

def test_debate_engine_logs_state(tmp_path):
    """Verify that DebateEngine appends logs and writes is_debating state to disk."""
    # Temporarily patch DEBATE_LOGS_PATH to write inside a temp folder
    import brain.debate_engine
    temp_logs_path = tmp_path / "debate_logs.json"
    brain.debate_engine.DEBATE_LOGS_PATH = temp_logs_path
    
    mock_model = MagicMock()
    mock_model.name = "Kimi"
    
    engine = DebateEngine(models=[mock_model])
    
    assert len(engine.current_logs) == 0
    engine._add_log("Test Log Event")
    
    assert len(engine.current_logs) == 1
    assert engine.current_logs[0] == "Test Log Event"
    
    # Read state file written to disk
    assert temp_logs_path.exists()
    with open(temp_logs_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["is_debating"] is True
    assert data["logs"] == ["Test Log Event"]

def test_get_search_config_for_model():
    """Verify that the engine falls back to default search configuration correctly."""
    mock_model = MagicMock()
    mock_model.name = "CustomModel"
    
    engine = DebateEngine(models=[mock_model])
    
    config = engine._get_search_config_for_model("CustomModel")
    assert config["enabled"] is True
    assert "General" in config["source"]
    assert "duckduckgo" in config["tools"]
