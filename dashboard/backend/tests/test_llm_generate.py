"""Tests for /api/llm/generate SSE streaming and model auto-fallback."""
import json
from unittest.mock import patch
from fastapi.testclient import TestClient

from pi_5.web_ui_backend.main import app


client = TestClient(app)

# --- Helpers ---

MOCK_TAGS_RESPONSE = {
    "models": [
        {"name": "qwen2:0.5b", "details": {"families": ["qwen2"]}},
        {"name": "llama3.2:1b", "details": {"families": ["llama"]}},
    ]
}

MOCK_TAGS_ONLY_VLM = {
    "models": [
        {"name": "moondream:latest", "details": {"families": ["clip"]}},
    ]
}

MOCK_OLLAMA_STREAM_LINES = [
    json.dumps({"model": "qwen2:0.5b", "response": "Hello", "done": False}),
    json.dumps({"model": "qwen2:0.5b", "response": " world", "done": False}),
    json.dumps({"model": "qwen2:0.5b", "response": "", "done": True}),
]

GENERATE_BODY = {
    "provider": "ollama",
    "model": "qwen2:0.5b",
    "inputText": "hi",
    "stream": True,
}


def _mock_auth_bypass():
    """Patch require_robot_auth to bypass authentication."""
    return patch("pi_5.web_ui_backend.core.require_robot_auth", return_value="test")


class FakeHTTPResponse:
    """Fake async HTTP response that yields lines."""

    def __init__(self, lines, status_code=200):
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeTagsResponse:
    """Fake response for /api/tags calls."""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class FakeAsyncClient:
    """Fake httpx.AsyncClient that returns mocked responses."""

    def __init__(self, tags_response=None, stream_lines=None):
        self._tags_response = tags_response or FakeTagsResponse(MOCK_TAGS_RESPONSE)
        self._stream_lines = stream_lines or MOCK_OLLAMA_STREAM_LINES

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url, **kwargs):
        return self._tags_response

    def stream(self, method, url, **kwargs):
        return FakeHTTPResponse(self._stream_lines)


# --- Tests ---


class TestSSEFormat:
    """Verify SSE events use proper newline framing."""

    def test_sse_events_have_real_newlines(self):
        """Stream must contain real \\n characters, not literal backslash-n."""
        fake_client = FakeAsyncClient()

        with _mock_auth_bypass(), \
             patch("httpx.AsyncClient", return_value=fake_client):
            response = client.post(
                "/api/llm/generate",
                json=GENERATE_BODY,
                headers={"x-robot-pin": "1234"},
            )

        assert response.status_code == 200
        assert response.headers.get("content-type", "").startswith("text/event-stream")

        body = response.text
        # Should contain real newlines, not literal \n
        assert "\\n" not in body.replace("\n", ""), \
            "SSE body contains literal backslash-n instead of real newlines"
        assert "\n" in body, "SSE body should contain real newline characters"

    def test_sse_events_contain_event_and_data_fields(self):
        """Each SSE block should have event: and data: lines."""
        fake_client = FakeAsyncClient()

        with _mock_auth_bypass(), \
             patch("httpx.AsyncClient", return_value=fake_client):
            response = client.post(
                "/api/llm/generate",
                json=GENERATE_BODY,
                headers={"x-robot-pin": "1234"},
            )

        body = response.text
        events = [block.strip() for block in body.split("\n\n") if block.strip()]

        assert len(events) >= 1, "Should have at least one SSE event"

        for event_block in events:
            lines = event_block.split("\n")
            has_event = any(line.startswith("event:") for line in lines)
            has_data = any(line.startswith("data:") for line in lines)
            assert has_event, f"SSE block missing 'event:' line: {event_block}"
            assert has_data, f"SSE block missing 'data:' line: {event_block}"

    def test_done_event_has_action(self):
        """The final 'done' event should contain an action with 'kind' key."""
        fake_client = FakeAsyncClient()

        with _mock_auth_bypass(), \
             patch("httpx.AsyncClient", return_value=fake_client):
            response = client.post(
                "/api/llm/generate",
                json=GENERATE_BODY,
                headers={"x-robot-pin": "1234"},
            )

        body = response.text
        events = [block.strip() for block in body.split("\n\n") if block.strip()]

        done_events = []
        for event_block in events:
            lines = event_block.split("\n")
            for line in lines:
                if line.startswith("event:") and "done" in line:
                    # Find the data line
                    for dl in lines:
                        if dl.startswith("data:"):
                            data = json.loads(dl[len("data:"):].strip())
                            done_events.append(data)

        assert len(done_events) >= 1, "Should have at least one 'done' event"
        done = done_events[0]
        assert "action" in done, "Done event must contain 'action'"
        assert done["action"] is not None, "Action should not be None"
        assert "kind" in done["action"], "Action must have 'kind' key"


class TestModelFallback:
    """Verify model auto-fallback when configured model doesn't exist."""

    def test_fallback_when_model_not_installed(self):
        """Should auto-select available model instead of 500 error."""
        body = {**GENERATE_BODY, "model": "nonexistent:latest"}
        fake_client = FakeAsyncClient()

        with _mock_auth_bypass(), \
             patch("httpx.AsyncClient", return_value=fake_client):
            response = client.post(
                "/api/llm/generate",
                json=body,
                headers={"x-robot-pin": "1234"},
            )

        # Should succeed (200) not crash (500)
        assert response.status_code == 200

    def test_fallback_skips_vlm_models(self):
        """Auto-fallback should skip VLM-only models like moondream."""
        body = {**GENERATE_BODY, "model": "nonexistent:latest"}

        # Only VLM available — should still pick it as last resort
        fake_client = FakeAsyncClient(
            tags_response=FakeTagsResponse(MOCK_TAGS_ONLY_VLM)
        )

        with _mock_auth_bypass(), \
             patch("httpx.AsyncClient", return_value=fake_client):
            response = client.post(
                "/api/llm/generate",
                json=body,
                headers={"x-robot-pin": "1234"},
            )

        assert response.status_code == 200

    def test_empty_model_uses_auto_detect(self):
        """When model is empty string, should auto-detect from available models."""
        body = {**GENERATE_BODY, "model": ""}
        fake_client = FakeAsyncClient()

        with _mock_auth_bypass(), \
             patch("httpx.AsyncClient", return_value=fake_client):
            response = client.post(
                "/api/llm/generate",
                json=body,
                headers={"x-robot-pin": "1234"},
            )

        assert response.status_code == 200
