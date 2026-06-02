import asyncio
import json

from brain.cognition.planner import LlmPlanner, build_planner
from brain.config import BrainConfig
from brain.memory.sqlite_memory import SqliteMemory
from brain.types import PerceptionState


def _cfg_with_ollama(tmp_path) -> BrainConfig:
    return BrainConfig(
        log_level="INFO",
        transport="mock",
        provider="ollama",
        esp32_tcp_host="127.0.0.1",
        esp32_tcp_port=8765,
        esp32_serial_port="",
        esp32_serial_baud=115200,
        memory_db_path=str(tmp_path / "brain.sqlite"),
        wake_word="aria",
        sleep_timeout_s=20.0,
        vosk_model_path="",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="dummy-model",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini",
        openai_api_key="",
        google_api_key="",
    )


def _cfg_with_openai(tmp_path) -> BrainConfig:
    return BrainConfig(
        log_level="INFO",
        transport="mock",
        esp32_tcp_host="127.0.0.1",
        esp32_tcp_port=8765,
        esp32_serial_port="",
        esp32_serial_baud=115200,
        memory_db_path=str(tmp_path / "brain.sqlite"),
        wake_word="aria",
        sleep_timeout_s=20.0,
        vosk_model_path="",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_model="",
        openai_base_url="https://api.openai.com/v1",
        openai_model="gpt-4o-mini",
        openai_api_key="test-key",
        google_api_key="",
    )


def test_rule_based_actions_still_work_when_ollama_enabled(tmp_path):
    cfg = _cfg_with_ollama(tmp_path)
    memory = SqliteMemory(cfg.memory_db_path)
    planner = build_planner(cfg, memory)

    action = asyncio.run(planner.plan(PerceptionState(ts_ms=0, text="sleep", vision=None, sensors=None, gestures=None)))
    assert action.kind == "set_state"
    assert action.payload["mode"] == "sleep"


def test_unknown_text_falls_back_to_ollama(tmp_path, monkeypatch):
    cfg = _cfg_with_ollama(tmp_path)
    memory = SqliteMemory(cfg.memory_db_path)
    planner = build_planner(cfg, memory)

    def _fake_ollama_json(self, system: str, user: str) -> str:
        return json.dumps({"kind": "set_led", "payload": {"id": 1, "state": "on"}})

    monkeypatch.setattr(LlmPlanner, "_ollama_json", _fake_ollama_json)
    action = asyncio.run(planner.plan(PerceptionState(ts_ms=0, text="please turn the light on", vision=None, sensors=None, gestures=None)))
    assert action.kind == "set_led"
    assert action.payload["state"] == "on"


def test_unknown_text_falls_back_to_openai(tmp_path, monkeypatch):
    cfg = _cfg_with_openai(tmp_path)
    memory = SqliteMemory(cfg.memory_db_path)
    planner = build_planner(cfg, memory)

    def _fake_openai_json(self, system: str, user: str) -> str:
        return json.dumps({"kind": "set_fan", "payload": {"state": "on"}})

    monkeypatch.setattr(LlmPlanner, "_openai_json", _fake_openai_json)
    action = asyncio.run(planner.plan(PerceptionState(ts_ms=0, text="it is hot", vision=None, sensors=None, gestures=None)))
    assert action.kind == "set_fan"
    assert action.payload["state"] == "on"


def test_llm_error_does_not_crash(tmp_path, monkeypatch):
    cfg = _cfg_with_ollama(tmp_path)
    memory = SqliteMemory(cfg.memory_db_path)
    planner = build_planner(cfg, memory)

    def _boom(self, system: str, user: str) -> str:
        raise TimeoutError("timed out")

    monkeypatch.setattr(LlmPlanner, "_ollama_json", _boom)
    action = asyncio.run(planner.plan(PerceptionState(ts_ms=0, text="aria كيف الحال", vision=None, sensors=None, gestures=None)))
    assert action.kind == "noop"
    assert action.payload.get("reason") == "llm_error"
