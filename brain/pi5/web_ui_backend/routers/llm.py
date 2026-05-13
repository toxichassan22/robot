import asyncio
import json
import re
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import core
from ..runtime_info import get_runtime_info

app = core.app


@app.post("/api/llm/generate")
async def generate(body: core.LLMGenerateBody, _auth: str = Depends(core.get_auth_dependency())):
    settings = await core.load_settings()
    base_url = body.ollamaBaseUrl or settings.ollamaBaseUrl
    model = body.model or settings.ollamaModel
    llm_num_gpu = core.num_gpu_for_device(settings.llmDevice, default=core.DEFAULT_LLM_DEVICE)
    vlm_patterns = ["moondream", "llava", "bakllava", "minicpm-v", "llama3.2-vision", "qwen-vl", "qwen3-vl", "qwen2.5-vl", "qwen2.5vl"]

    def _is_cloud_model(name: str) -> bool:
        """Detect if a model is cloud-hosted (runs on remote servers, not locally)."""
        n = str(name or "").strip().lower()
        return "-cloud" in n or ":cloud" in n or n.endswith("cloud")

    if not model:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url.rstrip('/')}/api/tags", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    for item in models:
                        name = item.get("name", "") if isinstance(item, dict) else str(item)
                        if not any(vlm in name.lower() for vlm in vlm_patterns):
                            model = name
                            break
                    if not model and models:
                        first = models[0]
                        model = first.get("name") if isinstance(first, dict) else str(first)
        except Exception:
            pass

    if model:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{base_url.rstrip('/')}/api/tags", timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
                    available = [
                        item.get("name", "") if isinstance(item, dict) else str(item)
                        for item in data.get("models", [])
                    ]
                    if model not in available:
                        for name in available:
                            if not any(vlm in name.lower() for vlm in vlm_patterns):
                                model = name
                                break
                        else:
                            if available:
                                model = available[0]
        except Exception:
            pass

    system_prompt = body.systemPrompt or (
        "You are a smart robot assistant. You must respond in strict JSON format.\n"
        "JSON Schema:\n"
        "{\n"
        '  "kind": "say" | "set_led" | "set_fan" | "set_state" | "noop",\n'
        '  "payload": {\n'
        '    "text": "Your response string here (if kind is say)",\n'
        "    ...other_args\n"
        "  }\n"
        "}\n"
        'Example:\n{"kind": "say", "payload": {"text": "Response text"}}'
    )
    if not body.systemPrompt:
        if settings.robotLanguage.startswith("ar"):
            system_prompt += "\nIMPORTANT: Reply in neutral Egyptian Arabic. Use calm, clear assistant phrasing. Avoid heavy slang and formal wording. Keep JSON keys unchanged. No emojis.         "
        else:
            system_prompt += "\nIMPORTANT: The 'text' field MUST be in English. Use concise, natural phrasing. DO NOT use emojis."
    elif settings.robotLanguage.startswith("ar") and "arabic" not in body.systemPrompt.lower() and "مصر" not in body.systemPrompt:
        system_prompt += "\nرد بمصرية طبيعية ومحايدة، واستخدم العربية فقط. كن واضحًا ومختصرًا. تجنب العامية المبالغ فيها والرسمية الزائدة. بدون رموز تعبيرية.  "

    def debug_log(message: str) -> None:
        core.DEBUG_LLM_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(core.DEBUG_LLM_PATH, "a", encoding="utf-8") as file_obj:
            file_obj.write(message + "\n")

    debug_log(f"--- Generate Request --- model: {model}, prompt: {body.inputText}")

    # Cloud models run on remote servers — don't send local resource options
    is_cloud = _is_cloud_model(model)
    if is_cloud:
        generate_options = {
            "temperature": 0.4,
        }
    else:
        generate_options = {
            "num_predict": 1024,
            "temperature": 0.4,
            "repeat_penalty": 1.5,
            "top_k": 50,
            "top_p": 0.95,
            "num_gpu": llm_num_gpu,
        }

    async def stream_generator():
        debug_log("stream_generator started")
        async with httpx.AsyncClient() as client:
            try:
                debug_log(f"Opening stream to {base_url.rstrip('/')}/api/generate (cloud={is_cloud})")
                async with client.stream(
                    "POST",
                    f"{base_url.rstrip('/')}/api/generate",
                    json={
                        "model": model,
                        "prompt": body.inputText,
                        "system": system_prompt,
                        "stream": True,
                        "options": generate_options,
                    },
                    timeout=120.0,
                ) as response:
                    debug_log(f"Response status: {response.status_code}")
                    response.raise_for_status()

                    full_text = ""
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            raw_token = chunk.get("response", "")
                            cleaned_token = ""
                            for char in raw_token:
                                cp = ord(char)
                                if 0x1F000 <= cp <= 0x1FFFF or 0x2600 <= cp <= 0x27BF or 0x2300 <= cp <= 0x25FF:
                                    continue
                                if char in ["?", "؟", "!", "¡"]:
                                    char = "."
                                cleaned_token += char

                            full_text += cleaned_token
                            if not chunk.get("done", False):
                                payload = {"outputText": cleaned_token, "action": None, "raw": chunk}
                                yield f"event: message\ndata: {json.dumps(payload)}\n\n"
                            else:
                                final_text = re.sub(r"<think>.*?</think>", "", full_text, flags=re.DOTALL).strip()
                                final_text = re.sub(
                                    r"(?im)^(?=.*(?:ممنوع|لا تستخدم|لا تستعمل|لا تكتب|التعليمات|القواعد|اللغة)).*$",
                                    "",
                                    final_text,
                                )
                                final_text = re.sub(r"\n{2,}", "\n", final_text).strip()
                                try:
                                    action = core.try_parse_action(final_text)
                                    if not action or "kind" not in action:
                                        action = {"kind": "say", "payload": {"text": final_text}}
                                except Exception:
                                    action = {"kind": "say", "payload": {"text": final_text}}

                                payload = {"outputText": "", "action": action, "raw": chunk}
                                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                        except Exception as exc:
                            debug_log(f"Parse error: {exc}")
                            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
            except Exception as exc:
                debug_log(f"Stream error: {exc}")
                yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
        debug_log("stream_generator finished")

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@app.get("/api/health/ollama")
async def health_ollama(baseUrl: Optional[str] = None):
    try:
        settings = await core.load_settings()
        target_url = baseUrl if baseUrl else (settings.ollamaBaseUrl or "http://127.0.0.1:11434")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{target_url.rstrip('/')}/api/tags", timeout=5.0)
            response.raise_for_status()
            return {"ok": True, "message": "Connected"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.get("/api/health")
async def health():
    now = time.time()
    offset_minutes = int(round((time.localtime().tm_gmtoff if hasattr(time.localtime(), "tm_gmtoff") else -time.timezone) / 60))
    runtime_info = await get_runtime_info()
    return {
        "success": True,
        "status": "ok",
        "freshAtMs": runtime_info.get("freshAtMs"),
        "ready": runtime_info.get("ready"),
        "degraded": runtime_info.get("degraded"),
        "errorCode": runtime_info.get("errorCode"),
        "message": runtime_info.get("message"),
        "serverTimeMs": int(now * 1000),
        "serverUtcOffsetMinutes": offset_minutes,
        "serverLocalHour": time.localtime(now).tm_hour,
        "host": runtime_info.get("host"),
        "services": runtime_info.get("services"),
    }


class V1CommandBody(BaseModel):
    type: str
    args: Optional[Dict[str, Any]] = None
    priority: Optional[str] = None
    ttl_ms: Optional[int] = None


@app.get("/v1/health")
async def v1_health():
    return {"ok": True}


@app.get("/v1/status")
async def v1_status():
    from .state import get_robot_status

    api_status = await get_robot_status()
    now_s = time.time()
    state = api_status.get("state") if isinstance(api_status, dict) else {}
    out: Dict[str, Any] = {
        "ok": bool(api_status.get("success")) if isinstance(api_status, dict) else False,
        "uptime_s": max(0, int(now_s - core.SERVER_STARTED_AT_S)),
        "status": state if isinstance(state, dict) else {},
        "timestamp_ms": int(now_s * 1000),
    }
    if isinstance(api_status, dict) and "heartbeat_healthy" in api_status:
        out["heartbeat_healthy"] = api_status["heartbeat_healthy"]
    if isinstance(api_status, dict) and api_status.get("error"):
        out["error"] = api_status["error"]
    return out


@app.post("/v1/commands")
async def v1_commands(body: V1CommandBody, _auth: str = Depends(core.get_auth_dependency())):
    payload = body.args or {}
    command_queue = core.get_command_queue()
    if command_queue is not None:
        await command_queue.put({"kind": body.type, "payload": payload})
        return {"ok": True, "queued": True, "type": body.type, "payload": payload}
    return {"ok": False, "queued": False, "error": "command_queue_unavailable", "type": body.type}


@app.post("/v1/stop")
async def v1_stop(_auth: str = Depends(core.get_auth_dependency())):
    from .motion import stop_motion

    return await stop_motion(_auth=_auth)


@app.get("/v1/events")
async def v1_events():
    async def gen():
        yield (f"data: {json.dumps({'type': 'hello', 'ts': time.time(), 'data': {'ok': True}})}\n\n").encode("utf-8")
        while True:
            yield b": keep-alive\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/llm/ollama-models")
async def get_ollama_models(baseUrl: Optional[str] = None):
    try:
        settings = await core.load_settings()
        target_url = baseUrl if baseUrl else (settings.ollamaBaseUrl or "http://127.0.0.1:11434")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{target_url.rstrip('/')}/api/tags", timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            models_raw = payload.get("models")
            if not isinstance(models_raw, list):
                return {"success": True, "models": []}
            models = [
                item["name"]
                for item in models_raw
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            ]
            return {"success": True, "models": models}
    except Exception as exc:
        return {"success": False, "error": str(exc), "models": []}


class PullRequest(BaseModel):
    name: str
    ollamaBaseUrl: Optional[str] = None


@app.post("/api/llm/ollama-pull")
async def pull_ollama_model(body: PullRequest, _auth: str = Depends(core.get_auth_dependency())):
    try:
        target_url = body.ollamaBaseUrl or "http://127.0.0.1:11434"
        from brain.llm.ollama_client import OllamaClient

        client = OllamaClient(base_url=target_url)

        def iter_stream():
            try:
                for chunk in client.pull_model(body.name):
                    yield chunk
            except Exception as exc:
                yield json.dumps({"error": str(exc)}).encode("utf-8") + b"\n"

        return StreamingResponse(iter_stream(), media_type="application/x-ndjson")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/vision/vlm-models")
async def get_vlm_models(baseUrl: Optional[str] = None):
    try:
        settings = await core.load_settings()
        target_url = baseUrl if baseUrl else (settings.vlmBaseUrl or "http://127.0.0.1:11434")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{target_url.rstrip('/')}/api/tags", timeout=10.0)
            response.raise_for_status()
            payload = response.json()
            models_raw = payload.get("models")
            if not isinstance(models_raw, list):
                return {"success": True, "models": []}

            models: list[str] = []
            for item in models_raw:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    continue
                name = item["name"].lower()
                details = item.get("details", {})
                families = details.get("families") if isinstance(details, dict) else None
                is_vision = isinstance(families, list) and "clip" in families
                if not is_vision and any(keyword in name for keyword in ["llava", "moondream", "vision", "minicpm", "yi-vl", "qwen-vl", "qwen3-vl", "qwen2.5-vl", "qwen2.5vl", "bakllava", "cam", "vlm"]):
                    is_vision = True
                if is_vision:
                    models.append(item["name"])
            return {"success": True, "models": models}
    except Exception as exc:
        return {"success": False, "error": str(exc), "models": []}


@app.get("/api/health/vlm")
async def health_vlm(baseUrl: Optional[str] = None):
    try:
        settings = await core.load_settings()
        target_url = baseUrl if baseUrl else (settings.vlmBaseUrl or "http://127.0.0.1:11434")
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{target_url.rstrip('/')}/api/tags", timeout=5.0)
            response.raise_for_status()
            return {"ok": True, "message": "Connected"}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@app.post("/api/vision/analyze")
async def analyze_vision(
    file: UploadFile = File(...),
    prompt: Optional[str] = "Describe this image",
    model: Optional[str] = None,
    baseUrl: Optional[str] = None,
    _auth: str = Depends(core.get_auth_dependency()),
):
    try:
        settings = await core.load_settings()
        content = await file.read()

        if model and baseUrl:
            # If explicit model and baseUrl are provided, use them directly (e.g. for testing specific endpoints)
            from brain.vision.vlm_client import VLMClient
            client = VLMClient(base_url=baseUrl)
            description = await client.analyze_image_async(
                model=model,
                image_bytes=content,
                prompt=prompt,
                device=settings.vlmDevice,
            )
        else:
            # Otherwise use the hybrid fallback logic from config
            from brain.config import BrainConfig
            from brain.vision.vlm_client import build_vlm
            
            cfg = BrainConfig.from_env().with_robot_settings(settings)
            vlm = build_vlm(cfg)
            
            # Use specific model if provided, otherwise use config defaults
            target_model = model if model else None
            
            description = await vlm.analyze_image_async(
                model=target_model or vlm.local_model,
                image_bytes=content,
                prompt=prompt,
                device=settings.vlmDevice,
            )

        return {"success": True, "description": description}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
