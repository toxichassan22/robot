from __future__ import annotations
import base64
import logging
from typing import Optional

try:
    from huggingface_hub import InferenceClient
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

logger = logging.getLogger("Brain.HFClient")


class HuggingFaceClient:
    """HuggingFace Inference client with automatic API key rotation.

    When a ``key_manager`` is provided the client will:
    1. Use the manager's current key for each request.
    2. On auth / quota errors, mark the key and rotate to the next one.
    3. Retry until all keys have been tried.

    If no ``key_manager`` is given it falls back to a single static key
    (backward-compatible with the old constructor signature).
    """

    def __init__(
        self,
        api_key: str = "",
        default_model: str = "",
        key_manager=None,  # type: Optional[HFKeyManager]  # noqa: F821
    ):
        self.default_model = default_model
        self._key_manager = key_manager
        self._static_key = api_key

        # Build the initial client
        effective_key = self._resolve_key()
        self.client = None
        if effective_key:
            self._rebuild_client(effective_key)
        elif not HF_AVAILABLE:
            logger.error("huggingface_hub is not installed and no key provided.")

    # ── internal helpers ─────────────────────────────────────────────

    def _resolve_key(self) -> str:
        """Return the key to use right now."""
        if self._key_manager is not None:
            return self._key_manager.get_current_key() or ""
        return self._static_key

    def _rebuild_client(self, key: str) -> None:
        """Create a fresh InferenceClient or OpenAI client for *key*."""
        if not key:
            return
            
        self._current_key = key
        if key.startswith("ms-"):
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://api-inference.modelscope.ai/v1",
                api_key=key
            )
            logger.info("Initialized ModelScope client for key starting with 'ms-'")
        elif key.startswith("sk-or-"):
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=key
            )
            logger.info("Initialized OpenRouter client for key starting with 'sk-or-'")
        elif key.startswith("sk-"):
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://api.siliconflow.com/v1",
                api_key=key
            )
            logger.info("Initialized SiliconFlow client for key starting with 'sk-'")
        elif HF_AVAILABLE:
            self.client = InferenceClient(api_key=key)
            logger.info("Initialized HuggingFace InferenceClient")
        else:
            from openai import OpenAI
            self.client = OpenAI(
                base_url="https://api-inference.huggingface.co/v1/",
                api_key=key
            )
            logger.info("Initialized HuggingFace OpenAI client")

    def _is_key_error(self, exc: Exception) -> str | None:
        """Classify the error — returns 'exhausted' / 'invalid' / None."""
        if self._key_manager is not None:
            from brain.llm.hf_key_manager import HFKeyManager
            return HFKeyManager.is_key_error(exc)
        return None

    # ── public API ───────────────────────────────────────────────────

    def chat(self, model: str, messages: list[dict], temperature: float = 0.2) -> str:
        if self.client is None and self._key_manager is None:
            raise RuntimeError("No API client available and no key manager configured")

        target_model = self.default_model if self.default_model else model

        # If we have a key manager, use retry-with-rotation logic
        if self._key_manager is not None:
            return self._chat_with_rotation(target_model, messages, temperature)

        # Legacy single-key path
        if self.client is None:
            raise RuntimeError("No HF API key configured")
        return self._do_chat(target_model, messages, temperature)

    def _chat_with_rotation(self, model: str, messages: list[dict], temperature: float) -> str:
        """Try the chat request, rotating keys on failure."""
        from brain.llm.hf_key_manager import HFKeyManager

        keys_status = self._key_manager.get_all_keys_status()
        max_attempts = max(len(keys_status), 1)

        last_error: Exception | None = None
        for attempt in range(max_attempts):
            current_key = self._key_manager.get_current_key()
            if not current_key:
                break

            self._rebuild_client(current_key)
            try:
                result = self._do_chat(model, messages, temperature)
                # Success — record it
                self._key_manager.record_success()
                return result
            except Exception as e:
                last_error = e
                error_type = HFKeyManager.is_key_error(e)
                if error_type:
                    logger.warning(
                        "HF key error (attempt %d/%d, type=%s): %s",
                        attempt + 1, max_attempts, error_type, str(e)[:120],
                    )
                    new_key = self._key_manager.mark_current_exhausted_and_rotate(
                        status=error_type
                    )
                    if new_key is None:
                        break
                    # Continue loop with the new key
                else:
                    # Not a key error — don't rotate, just raise
                    raise

        raise RuntimeError(
            f"All HF API keys exhausted after {max_attempts} attempts. "
            f"Last error: {last_error}"
        )

    def _do_chat(self, model: str, messages: list[dict], temperature: float) -> str:
        """Execute the actual chat completion request."""
        key = getattr(self, "_current_key", "")
        if key and not key.startswith("sk-or-") and not key.startswith("sk-") and not key.startswith("ms-"):
            hf_map = {
                "mistralai/mistral-7b-instruct:free": "mistralai/Mistral-7B-Instruct-v0.3",
                "google/gemini-2.5-flash:free": "google/gemma-2-9b-it",
                "qwen/qwen-2.5-72b-instruct:free": "Qwen/Qwen2.5-72B-Instruct",
                "meta-llama/llama-3.3-70b-instruct:free": "meta-llama/Llama-3.2-11B-Vision-Instruct",
                "deepseek/deepseek-r1:free": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
            }
            if model in hf_map:
                model = hf_map[model]

        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        
        content = completion.choices[0].message.content
        if not content:
            # Fallback if content is None but reasoning exists (some APIs return it differently)
            content = getattr(completion.choices[0].message, "reasoning", "") or ""
            
        return content

    def analyze_image(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        if self.client is None and self._key_manager is None:
            raise RuntimeError("No API client available and no key manager configured")

        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        data_uri = f"data:image/jpeg;base64,{b64_img}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ]
            }
        ]

        target_model = self.default_model if self.default_model else model

        # With key manager — retry with rotation
        if self._key_manager is not None:
            return self._image_with_rotation(target_model, messages)

        # Legacy single-key path
        if self.client is None:
            raise RuntimeError("No HF API key configured")
        return self._do_image(target_model, messages)

    def _image_with_rotation(self, model: str, messages: list[dict]) -> str:
        """Try image analysis, rotating keys on failure."""
        from brain.llm.hf_key_manager import HFKeyManager

        keys_status = self._key_manager.get_all_keys_status()
        max_attempts = max(len(keys_status), 1)

        last_error: Exception | None = None
        for attempt in range(max_attempts):
            current_key = self._key_manager.get_current_key()
            if not current_key:
                break

            self._rebuild_client(current_key)
            try:
                result = self._do_image(model, messages)
                self._key_manager.record_success()
                return result
            except Exception as e:
                last_error = e
                error_type = HFKeyManager.is_key_error(e)
                if error_type:
                    logger.warning(
                        "HF image key error (attempt %d/%d, type=%s): %s",
                        attempt + 1, max_attempts, error_type, str(e)[:120],
                    )
                    new_key = self._key_manager.mark_current_exhausted_and_rotate(
                        status=error_type
                    )
                    if new_key is None:
                        break
                else:
                    raise

        raise RuntimeError(
            f"All HF API keys exhausted for image analysis. Last error: {last_error}"
        )

    def _do_image(self, model: str, messages: list[dict]) -> str:
        """Execute the actual image analysis request."""
        key = getattr(self, "_current_key", "")
        if key and not key.startswith("sk-or-") and not key.startswith("sk-") and not key.startswith("ms-"):
            hf_map = {
                "mistralai/mistral-7b-instruct:free": "mistralai/Mistral-7B-Instruct-v0.3",
                "google/gemini-2.5-flash:free": "google/gemma-2-9b-it",
                "qwen/qwen-2.5-72b-instruct:free": "Qwen/Qwen2.5-72B-Instruct",
                "meta-llama/llama-3.3-70b-instruct:free": "meta-llama/Llama-3.2-11B-Vision-Instruct",
                "deepseek/deepseek-r1:free": "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
            }
            if model in hf_map:
                model = hf_map[model]

        completion = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        
        content = completion.choices[0].message.content
        if not content:
            content = getattr(completion.choices[0].message, "reasoning", "") or ""
            
        return content

    async def analyze_image_async(self, model: str, image_bytes: bytes, prompt: str = "Describe this image", device: str = "gpu") -> str:
        import asyncio
        return await asyncio.to_thread(self.analyze_image, model, image_bytes, prompt, device)
