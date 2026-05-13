from __future__ import annotations

import time
from dataclasses import dataclass

from brain.types import ActionCommand, PerceptionState


@dataclass
class WakeWordDecision:
    should_plan: bool
    immediate_action: ActionCommand | None
    rewritten_text: str | None = None


@dataclass
class WakeWordGate:
    wake_word: str
    sleep_timeout_s: float
    is_awake: bool = False
    last_active_monotonic: float = 0.0

    def _norm(self, text: str) -> str:
        return " ".join(text.strip().lower().split())

    def _contains_wake_word(self, text: str) -> bool:
        ww = self._norm(self.wake_word)
        if not ww:
            return True
        t = self._norm(text)
        return ww in t

    def _strip_wake_word(self, text: str) -> str:
        ww = self._norm(self.wake_word)
        if not ww:
            return text.strip()
        t = self._norm(text)
        i = t.find(ww)
        if i < 0:
            return text.strip()
        left = (t[:i] + " " + t[i + len(ww) :]).strip()
        return left

    def on_perception(self, perception: PerceptionState) -> WakeWordDecision:
        now = time.monotonic()
        if self.is_awake and self.sleep_timeout_s > 0 and self.last_active_monotonic:
            if now - self.last_active_monotonic >= self.sleep_timeout_s:
                self.is_awake = False
                return WakeWordDecision(
                    should_plan=False,
                    immediate_action=ActionCommand(kind="set_state", payload={"mode": "sleep", "eye": "closed"}),
                )

        text = (perception.text or "").strip()
        if not text:
            return WakeWordDecision(should_plan=False, immediate_action=None)

        if not self.is_awake:
            if self._contains_wake_word(text):
                self.is_awake = True
                self.last_active_monotonic = now
                remainder = self._strip_wake_word(text)
                if remainder:
                    return WakeWordDecision(
                        should_plan=True,
                        immediate_action=ActionCommand(kind="set_state", payload={"mode": "awake", "eye": "open"}),
                        rewritten_text=remainder,
                    )
                return WakeWordDecision(
                    should_plan=False,
                    immediate_action=ActionCommand(kind="set_state", payload={"mode": "awake", "eye": "open"}),
                )
            return WakeWordDecision(should_plan=False, immediate_action=None)

        self.last_active_monotonic = now
        return WakeWordDecision(should_plan=True, immediate_action=None, rewritten_text=None)
