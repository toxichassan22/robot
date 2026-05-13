from __future__ import annotations

import json
import urllib.error
import urllib.request


class OpenAIClient:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def chat(self, model: str, messages: list[dict], temperature: float = 0.2) -> str:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI HTTP {e.code}: {raw[:300]}")
        except Exception as e:
            raise RuntimeError(f"OpenAI request failed: {e}")

        try:
            return data["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError(f"OpenAI unexpected response: {str(data)[:300]}")

