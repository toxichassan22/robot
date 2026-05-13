from __future__ import annotations

import json
import logging
import re
import urllib.request
import urllib.error
import base64

OLLAMA_VLM_TIMEOUT_S = 180


def _num_gpu_for_device(device: str) -> int:
    return -1 if str(device or "").strip().lower() == "gpu" else 0


def _is_cloud_model(model: str) -> bool:
    """Detect if a model is cloud-hosted (runs on remote servers, not locally)."""
    name = str(model or "").strip().lower()
    return "-cloud" in name or ":cloud" in name or name.endswith("cloud")


def _ollama_vlm_options(model: str, device: str) -> dict:
    model_name = str(model or "").strip().lower()
    # Cloud models run on remote servers — don't send local resource options
    if _is_cloud_model(model):
        return {"temperature": 0.0}
    options = {
        "num_gpu": _num_gpu_for_device(device),
        "temperature": 0.0,
        "num_predict": 96,
    }
    if "qwen" in model_name:
        options["num_ctx"] = 1024
        options["num_predict"] = 64
    else:
        options["num_ctx"] = 2048
    return options


def _is_chat_vlm_model(model: str) -> bool:
    model_name = str(model or "").strip().lower()
    return "qwen" in model_name


def _fallback_from_thinking(message: dict) -> str:
    content = str(message.get("content") or "").strip()
    if content:
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        if content:
            return content

    thinking = re.sub(r"\s+", " ", str(message.get("thinking") or "")).strip()
    if not thinking:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", thinking)
    kept: list[str] = []
    for sentence in sentences:
        text = sentence.strip(" ,")
        if not text:
            continue
        lowered = text.lower()
        if lowered.startswith(("got it", "let's", "wait", "the question", "let me", "so ", "need to", "okay")):
            continue
        if any(
            token in lowered
            for token in ("person", "wear", "hair", "glasses", "shirt", "top", "text", "background", "object", "left", "right", "color", "clothes", "visible", "blanket", "pillow")
        ):
            kept.append(text)
        if len(kept) >= 2:
            break
    if kept:
        return " ".join(kept)
    return thinking[:280].strip()


class VLMClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> list[str]:
        """List available models from Ollama (VLM uses the same Ollama instance)"""
        url = self.base_url + "/api/tags"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama VLM HTTP {e.code}: {raw[:300]}")
        except Exception as e:
            raise RuntimeError(f"Ollama VLM request failed: {e}")
        
        models = payload.get("models")
        if not isinstance(models, list):
            return []
        out: list[str] = []
        for m in models:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                out.append(m["name"])
        return out

    def analyze_image(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        if _is_chat_vlm_model(model):
            url = self.base_url + "/api/chat"
            body = {
                "model": model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64_img],
                    }
                ],
                "options": _ollama_vlm_options(model, device),
            }
        else:
            url = self.base_url + "/api/generate"
            body = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "images": [b64_img],
                "options": _ollama_vlm_options(model, device),
            }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        
        try:
            with urllib.request.urlopen(req, timeout=OLLAMA_VLM_TIMEOUT_S) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama VLM HTTP {e.code}: {raw[:300]}")
        except Exception as e:
            raise RuntimeError(f"Ollama VLM request failed: {e}")
            
        if _is_chat_vlm_model(model):
            message = payload.get("message")
            if isinstance(message, dict):
                return _fallback_from_thinking(message)
            return ""
        return payload.get("response", "").strip()

    async def analyze_image_async(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        if _is_chat_vlm_model(model):
            url = self.base_url + "/api/chat"
            body = {
                "model": model,
                "stream": False,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64_img],
                    }
                ],
                "options": _ollama_vlm_options(model, device),
            }
        else:
            url = self.base_url + "/api/generate"
            body = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "images": [b64_img],
                "options": _ollama_vlm_options(model, device),
            }
        
        import httpx
        try:
            async with httpx.AsyncClient(timeout=float(OLLAMA_VLM_TIMEOUT_S)) as client:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                payload = resp.json()
                if _is_chat_vlm_model(model):
                    message = payload.get("message")
                    if isinstance(message, dict):
                        return _fallback_from_thinking(message)
                    return ""
                return payload.get("response", "").strip()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Ollama VLM async HTTP {e.response.status_code}: {e.response.text[:300]}")
        except Exception as e:
            raise RuntimeError(f"Ollama VLM async request failed: {e}")


class FallbackVLMClient:
    """A VLM client that attempts to use a cloud VLM first, falling back to local Ollama if it fails or is disabled."""
    def __init__(self, cloud_url: str, cloud_model: str, local_url: str, local_model: str, online_enabled: bool = True):
        self.cloud_client = VLMClient(base_url=cloud_url) if cloud_url else None
        self.local_client = VLMClient(base_url=local_url)
        self.cloud_model = cloud_model
        self.local_model = local_model
        self.online_enabled = online_enabled

    def list_models(self) -> list[str]:
        # Usually we only care about local models for listing in a UI
        return self.local_client.list_models()

    def analyze_image(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        # If model is explicitly passed, we use the requested client logic
        # But usually we follow the internal fallback logic
        if self.online_enabled and self.cloud_client and self.cloud_model:
            try:
                logging.info(f"VLM: Attempting cloud analysis with {self.cloud_model}...")
                return self.cloud_client.analyze_image(self.cloud_model, image_bytes, prompt, device)
            except Exception as e:
                logging.warning(f"VLM: Cloud analysis failed, falling back to local: {e}")
        
        logging.info(f"VLM: Using local analysis with {self.local_model}...")
        return self.local_client.analyze_image(self.local_model, image_bytes, prompt, device)

    async def analyze_image_async(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        if self.online_enabled and self.cloud_client and self.cloud_model:
            try:
                logging.info(f"VLM: Attempting cloud analysis (async) with {self.cloud_model}...")
                return await self.cloud_client.analyze_image_async(self.cloud_model, image_bytes, prompt, device)
            except Exception as e:
                logging.warning(f"VLM: Cloud async analysis failed, falling back to local: {e}")
        
        logging.info(f"VLM: Using local analysis (async) with {self.local_model}...")
        return await self.local_client.analyze_image_async(self.local_model, image_bytes, prompt, device)


def build_vlm(cfg) -> FallbackVLMClient | any:
    """Factory function to create a VLM Client from config."""
    model = str(cfg.vlm_model or "").strip().lower()
    
    if cfg.hf_api_key:
        from brain.llm.huggingface_client import HuggingFaceClient
        return HuggingFaceClient(api_key=cfg.hf_api_key, default_model=cfg.hf_model)
        
    if "gemini" in model:
        from brain.llm.gemini_client import GeminiClient
        return GeminiClient(api_key=cfg.google_api_key)
        
    return FallbackVLMClient(
        cloud_url=cfg.vlm_cloud_url,
        cloud_model=cfg.vlm_cloud_model,
        local_url=cfg.vlm_base_url,
        local_model=cfg.vlm_model,
        online_enabled=cfg.vlm_online_enabled,
    )
