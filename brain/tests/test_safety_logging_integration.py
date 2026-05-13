import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, asdict

# Mock necessary classes to avoid full initialization
@dataclass
class MockAction:
    kind: str
    payload: dict

@dataclass
class MockRules:
    pass

@dataclass
class ValidationResult:
    is_safe: bool
    was_modified: bool
    reason: str
    safe_command: MockAction

class MockSafeExecutor:
    async def execute(self, command):
        pass

# We will patch BrainRuntime to avoid its __init__
from brain.runtime import BrainRuntime


def test_log_safety_event():
    async def _run():
        with patch("brain.runtime.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            class TestBrain(BrainRuntime):
                def __init__(self):
                    self.safe_executor = AsyncMock()
                    self.gate = MagicMock()
                    self.planner = AsyncMock()
                    self.memory = AsyncMock()
                    self.feedback = AsyncMock()
                    self.transport = MagicMock()
                    self.esp32 = MagicMock()
                    self.cfg = MagicMock()
                    self.cfg.gesture_detection_enabled = False

            brain = TestBrain()
            original_cmd = {"kind": "motion", "payload": {"speed": 2.0}}
            safe_cmd = {"kind": "motion", "payload": {"speed": 1.0}}
            reason = "Speed limited"

            await brain._log_safety_event("command_override", reason, original_cmd, safe_cmd)

            mock_client.post.assert_called_once()
            _, kwargs = mock_client.post.call_args
            assert kwargs["json"]["event"] == "command_override"
            assert kwargs["json"]["reason"] == reason
            assert kwargs["json"]["original"] == original_cmd
            assert kwargs["json"]["safe"] == safe_cmd

    asyncio.run(_run())


def test_handle_perception_safety_logging():
    async def _run():
        with patch("brain.runtime.BrainRuntime._log_safety_event", new_callable=AsyncMock) as mock_log:
            class TestBrain(BrainRuntime):
                def __init__(self):
                    self.safe_executor = AsyncMock()
                    self.gate = MagicMock()
                    self.planner = AsyncMock()
                    self.memory = AsyncMock()
                    self.feedback = AsyncMock()
                    self.transport = MagicMock()
                    self.esp32 = MagicMock()
                    self.cfg = MagicMock()
                    self.cfg.gesture_detection_enabled = False

            brain = TestBrain()
            perception = MagicMock()
            perception.text = "run forward fast"
            perception.gestures = []

            decision = MagicMock()
            decision.immediate_action = MockAction(kind="motion", payload={"speed": 2.0})
            decision.should_plan = False
            decision.rewritten_text = None
            brain.gate.on_perception.return_value = decision

            safe_cmd = MockAction(kind="motion", payload={"speed": 1.0})
            val_result = ValidationResult(is_safe=True, was_modified=True, reason="Too fast", safe_command=safe_cmd)
            brain.safe_executor.execute.return_value = val_result

            await brain.handle_perception(perception)

            mock_log.assert_called_once()
            _, kwargs = mock_log.call_args
            assert kwargs["event_type"] == "command_override"
            assert kwargs["reason"] == "Too fast"
            assert kwargs["original"] == asdict(decision.immediate_action)
            assert kwargs["safe"] == asdict(safe_cmd)

    asyncio.run(_run())

