import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np
from brain.speech.gemini_live_vision import run_vision_channel, build_deep_analysis_tool

@pytest.mark.asyncio
async def test_vision_channel_tool_call():
    # Mock camera
    mock_camera = MagicMock()
    mock_camera.get_latest_frame.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

    # Mock Gemini Session
    mock_session = AsyncMock()
    
    # Mock tool call response
    class MockCall:
        def __init__(self, name, args):
            self.name = name
            self.args = args

    class MockToolCall:
        def __init__(self, function_calls):
            self.function_calls = function_calls

    class MockResponse:
        def __init__(self, tool_call=None, text=None):
            self.tool_call = tool_call
            self.text = text

    mock_tool_call = MockToolCall([MockCall("request_deep_visual_analysis", {"reason": "test reason", "focus": "test focus"})])
    
    # We want the receive loop to return one tool call and then hang or exit
    async def mock_receive():
        yield MockResponse(tool_call=mock_tool_call)
        # Wait a bit to allow the send_loop to run at least once
        await asyncio.sleep(0.5)
        raise asyncio.CancelledError()

    mock_session.receive = mock_receive

    # Mock client and connect
    mock_client = MagicMock()
    mock_client.aio.live.connect.return_value.__aenter__.return_value = mock_session

    # Callbacks
    tool_call_received = asyncio.Event()
    received_args = {}

    async def on_tool_call(reason, focus):
        received_args["reason"] = reason
        received_args["focus"] = focus
        tool_call_received.set()

    on_text_response = MagicMock()

    with patch("brain.speech.gemini_live_vision.create_live_client", return_value=mock_client):
        # Run with a small FPS to avoid too many sends
        task = asyncio.create_task(run_vision_channel(
            api_key="fake_key",
            model_id="fake_model",
            camera=mock_camera,
            fps=1,
            on_tool_call=on_tool_call,
            on_text_response=on_text_response
        ))

        try:
            # Wait for tool call to be processed
            await asyncio.wait_for(tool_call_received.wait(), timeout=2.0)
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    assert received_args["reason"] == "test reason"
    assert received_args["focus"] == "test focus"
    assert mock_camera.get_latest_frame.called
    assert mock_session.send_realtime_input.called

if __name__ == "__main__":
    pytest.main([__file__])
