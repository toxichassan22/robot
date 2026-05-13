import asyncio
import httpx
import json
import os
import logging
from typing import Optional

logger = logging.getLogger("Brain.Models")

class LLMWrapper:
    def __init__(self, name: str, base_url: str, model_name: str, api_key: str = "", timeout: Optional[float] = None):
        self.name = name
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Simple Ollama/OpenAI compatible payload
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False
        }
        
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        endpoint = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        if "11434" in self.base_url: # Ollama
            endpoint = f"{self.base_url.rstrip('/')}/api/chat"

        logger.debug(f"[{self.name}] Sending request to {endpoint}...")
        
        try:
            async with httpx.AsyncClient() as client:
                request_timeout = self.timeout
                if request_timeout is None:
                    # No time limit on reading response - let models think as long as they need
                    # But keep reasonable connect/write timeouts to detect network issues
                    request_timeout = httpx.Timeout(connect=30.0, read=None, write=60.0, pool=30.0)
                response = await client.post(
                    endpoint, 
                    json=payload, 
                    headers=headers, 
                    timeout=request_timeout
                )
                response.raise_for_status()
                data = response.json()
                
                # Handle Ollama vs OpenAI format
                if "message" in data:
                    return data["message"]["content"]
                elif "choices" in data:
                    return data["choices"][0]["message"]["content"]
                return str(data)
                
        except (asyncio.TimeoutError, httpx.TimeoutException) as e:
            # Only timeout on connect/write (network issues), not on read (model thinking)
            timeout_desc = f"{self.timeout}s" if self.timeout is not None else "no limit (network timeout)"
            logger.warning(f"[{self.name}] Network timeout after {timeout_desc}: {str(e)}")
            raise TimeoutError(f"{self.name} network timeout: {str(e)}")
        except Exception as e:
            logger.error(f"[{self.name}] Error: {str(e)}")
            raise e

class HuggingFaceLLMWrapper:
    def __init__(self, name: str, model_name: str, hf_client):
        self.name = name
        self.model_name = model_name
        self.hf_client = hf_client

    async def generate(self, prompt: str, system_prompt: str = "") -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        logger.debug(f"[{self.name}] Sending request to HuggingFace (model: {self.model_name})...")
        
        try:
            # chat is synchronous, so we run it in a thread to not block the event loop
            import asyncio
            result = await asyncio.to_thread(
                self.hf_client.chat,
                model=self.model_name,
                messages=messages,
                temperature=0.2
            )
            return result
        except Exception as e:
            logger.error(f"[{self.name}] Error: {str(e)}")
            raise e

# Instantiate the 5 debate models — all running through Ollama cloud proxy
# Instantiate the 5 debate models
OLLAMA_URL = os.getenv("OLLAMA_CLOUD_URL", "http://127.0.0.1:11434")

# Set up the HuggingFace client with the automatic key manager
from brain.pi5.web_ui_backend.routers.api_keys import _get_key_manager
from brain.llm.huggingface_client import HuggingFaceClient
hf_client = HuggingFaceClient(default_model="arcee-ai/trinity-large-thinking:free", key_manager=_get_key_manager())

# Main Brain Model (Trinity via OpenRouter)
deepseek = HuggingFaceLLMWrapper("Trinity", "arcee-ai/trinity-large-thinking:free", hf_client)

# Secondary Models (Ollama)
minimax = LLMWrapper("Minimax", OLLAMA_URL, "minimax-m2.7:cloud", timeout=None)
qwen = LLMWrapper("Qwen", OLLAMA_URL, "qwen3.5:397b-cloud", timeout=None)
nemotron = LLMWrapper("Nemotron", OLLAMA_URL, "nemotron-3-super:cloud", timeout=None)
glm = LLMWrapper("GLM", OLLAMA_URL, "glm-4.7:cloud", timeout=None)

ALL_MODELS = [deepseek, minimax, qwen, nemotron, glm]
