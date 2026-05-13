from __future__ import annotations

import os
from google import genai

DEFAULT_LIVE_MODEL = "gemini-3.1-flash-live-preview"

def require_single_gemini_api_key(api_key: str | None = None, env_var: str = "BRAIN_GEMINI_API_KEY") -> str:
    value = str(api_key or os.getenv(env_var, "")).strip()
    if not value:
        raise RuntimeError(f"{env_var} is empty. Set one fixed Gemini API key in config/.env.")
    if "," in value:
        raise RuntimeError(f"{env_var} contains multiple keys. Keep only one fixed key.")
    return value

def resolve_live_model(model: str | None = None) -> str:
    value = str(model or os.getenv("BRAIN_GEMINI_LIVE_MODEL", "")).strip()
    return value or DEFAULT_LIVE_MODEL

def create_live_client(api_key: str | None = None, env_var: str = "BRAIN_GEMINI_API_KEY") -> genai.Client:
    return genai.Client(api_key=require_single_gemini_api_key(api_key, env_var))
