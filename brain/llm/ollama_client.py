from __future__ import annotations

import json
import urllib.error
import urllib.request


def _num_gpu_for_device(device: str) -> int:
    return -1 if str(device or "").strip().lower() == "gpu" else 0


def _is_cloud_model(model: str) -> bool:
    """Detect if a model is cloud-hosted (runs on remote servers, not locally)."""
    name = str(model or "").strip().lower()
    return "-cloud" in name or ":cloud" in name or name.endswith("cloud")


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[str]:
        url = self.base_url + "/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        models = payload.get("models")
        if not isinstance(models, list):
            return []
        out: list[str] = []
        for m in models:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                out.append(m["name"])
        return out

    def chat(self, model: str, messages: list[dict], temperature: float = 0.2, device: str = "cpu") -> str:
        url = self.base_url + "/api/chat"
        # Cloud models run on remote servers — don't send local resource options
        if _is_cloud_model(model):
            options = {"temperature": temperature}
        else:
            options = {"temperature": temperature, "num_gpu": _num_gpu_for_device(device)}
        body = {
            "model": model,
            "stream": False,
            "messages": messages,
            "options": options,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {e.code}: {raw[:300]}")
        except Exception as e:
            raise RuntimeError(f"Ollama request failed: {e}")
        msg = (payload.get("message") or {}).get("content")
        return msg.strip() if isinstance(msg, str) else ""

    def pull_model(self, model: str) -> any:
        """
        Triggers a model pull and yields the raw bytes from the stream.
        """
        url = self.base_url + "/api/pull"
        # stream=True by default in ollama api usually, but let's be explicit
        body = {"name": model, "stream": True}
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        try:
            resp = urllib.request.urlopen(req, timeout=3600)
            return resp
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Ollama pull failed: {e}")
