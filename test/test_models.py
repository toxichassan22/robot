import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def test_debate_models_configurations():
    """Verify that all debate models are defined and correctly named in brain.models."""
    from brain.models import ALL_MODELS, deepseek, minimax, qwen, nemotron, glm
    
    assert len(ALL_MODELS) == 5
    assert deepseek.name == "Kimi"
    assert deepseek.model_name == "moonshotai/kimi-k2.6:free"
    
    assert minimax.name == "Minimax"
    assert minimax.model_name == "minimax-m2.7:cloud"
    
    assert qwen.name == "Qwen"
    assert qwen.model_name == "qwen3.5:397b-cloud"
    
    assert nemotron.name == "Nemotron"
    assert nemotron.model_name == "nemotron-3-super:cloud"
    
    assert glm.name == "GLM"
    assert glm.model_name == "glm-4.7:cloud"

import pytest

@pytest.mark.anyio
async def test_hf_llm_wrapper_generate():
    """Verify that HuggingFaceLLMWrapper handles system prompts and calls the client correctly."""
    from brain.llm.huggingface_client import HuggingFaceClient
    from brain.models import HuggingFaceLLMWrapper
    
    # Mock the HuggingFaceClient
    mock_client = MagicMock()
    mock_client.chat = MagicMock(return_value="مرحباً")
    
    wrapper = HuggingFaceLLMWrapper(
        name="TestKimi", 
        model_name="moonshotai/kimi-k2.6:free", 
        hf_client=mock_client
    )
    
    result = await wrapper.generate("مرحبا", "كن مساعدا لطيفا")
    assert result == "مرحباً"
    
    # Verify the client chat was called with expected arguments
    mock_client.chat.assert_called_once()
    kwargs = mock_client.chat.call_args[1]
    assert kwargs["model"] == "moonshotai/kimi-k2.6:free"
    assert kwargs["temperature"] == 0.2
    assert len(kwargs["messages"]) == 2
    assert kwargs["messages"][0] == {"role": "system", "content": "كن مساعدا لطيفا"}
    assert kwargs["messages"][1] == {"role": "user", "content": "مرحبا"}
