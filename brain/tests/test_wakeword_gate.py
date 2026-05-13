import time

from brain.cognition.wakeword_gate import WakeWordGate
from brain.types import PerceptionState


def _p(text: str | None) -> PerceptionState:
    return PerceptionState(ts_ms=0, text=text, vision=None, sensors=None, gestures=None)


def test_sleep_ignores_until_wake_word():
    g = WakeWordGate(wake_word="aria", sleep_timeout_s=10)

    d1 = g.on_perception(_p("hello"))
    assert d1.should_plan is False
    assert d1.immediate_action is None

    d2 = g.on_perception(_p("aria"))
    assert d2.should_plan is False
    assert d2.immediate_action is not None
    assert d2.immediate_action.payload["mode"] == "awake"

    d3 = g.on_perception(_p("turn on led"))
    assert d3.should_plan is True
    assert d3.immediate_action is None


def test_wake_word_with_command_in_same_phrase():
    g = WakeWordGate(wake_word="aria", sleep_timeout_s=10)
    d = g.on_perception(_p("aria turn on the fan"))
    assert d.immediate_action is not None
    assert d.immediate_action.payload["mode"] == "awake"
    assert d.should_plan is True
    assert d.rewritten_text == "turn on the fan"


def test_goes_back_to_sleep_after_timeout():
    g = WakeWordGate(wake_word="aria", sleep_timeout_s=0.1)
    g.on_perception(_p("aria"))
    time.sleep(0.12)
    d = g.on_perception(_p(""))
    assert d.should_plan is False
    assert d.immediate_action is not None
    assert d.immediate_action.payload["mode"] == "sleep"
