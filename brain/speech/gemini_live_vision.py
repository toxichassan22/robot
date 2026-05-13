from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import cv2
import numpy as np
from google.genai import types

from brain.speech.gemini_live_common import create_live_client, resolve_live_model

logger = logging.getLogger(__name__)

def build_deep_analysis_tool() -> types.Tool:
    """Builds the request_deep_visual_analysis tool declaration."""
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="request_deep_visual_analysis",
                description=(
                    "Request deep, high-precision visual analysis from the Qwen expert system. "
                    "Use ONLY when the scene contains details that require maximum accuracy "
                    "(text, numbers, prescriptions, faces, fine details)."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "reason": types.Schema(
                            type="STRING",
                            description="لماذا التحليل العميق ضروري الآن"
                        ),
                        "focus": types.Schema(
                            type="STRING",
                            description="على ماذا يجب أن يركز Qwen (مثل: 'النص في الورقة' / 'وجه الشخص اليمين')"
                        ),
                    },
                    required=["reason", "focus"],
                ),
            )
        ]
    )

def build_live_vision_config(
    system_instruction: str | None = None,
    tools: list[types.Tool] | None = None,
) -> types.LiveConnectConfig:
    """Builds the LiveConnectConfig for the vision channel (Channel B)."""
    if system_instruction is None:
        system_instruction = (
            "إنت Watchman شغال 24/7. لو شفت حاجة محتاجة دقة عالية "
            "(نص/روشتة/أرقام/تفاصيل دقيقة)، استدع request_deep_visual_analysis."
        )
    
    if tools is None:
        tools = [build_deep_analysis_tool()]

    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(parts=[types.Part.from_text(text=system_instruction)]),
        tools=tools,
    )

def encode_frame_to_jpeg(bgr_frame: np.ndarray, quality: int = 70, max_dim: int = 720) -> bytes | None:
    """Encodes a BGR frame to JPEG format."""
    try:
        # Resize if necessary
        h, w = bgr_frame.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            bgr_frame = cv2.resize(bgr_frame, (new_w, new_h))
        
        success, jpeg_bytes = cv2.imencode(".jpg", bgr_frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if success:
            return jpeg_bytes.tobytes()
    except Exception as e:
        logger.error(f"Failed to encode frame to JPEG: {e}")
    return None

async def send_frame_to_gemini(session: Any, jpeg_bytes: bytes) -> None:
    """Sends a JPEG frame to the Gemini Live session."""
    await session.send_realtime_input(
        video=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
    )

async def run_vision_channel(
    api_key: str | None,
    model_id: str | None,
    camera: Any,
    fps: float,
    on_tool_call: Callable[[str, str], Any],
    on_text_response: Callable[[str], Any],
) -> None:
    """Main loop for the Gemini Live Vision Channel (Channel B)."""
    client = create_live_client(api_key, env_var="BRAIN_VISION_API_KEY")
    model = resolve_live_model(model_id)
    config = build_live_vision_config()

    logger.info("Connecting to Gemini Live Vision Channel (Channel B)...")
    
    async with client.aio.live.connect(model=model, config=config) as session:
        logger.info("Vision channel connected.")

        async def send_loop():
            interval = 1.0 / fps
            while True:
                frame = camera.get_latest_frame()
                if frame is not None:
                    jpeg_bytes = encode_frame_to_jpeg(frame)
                    if jpeg_bytes:
                        try:
                            await send_frame_to_gemini(session, jpeg_bytes)
                            logger.debug(f"Frame sent ({len(jpeg_bytes)} bytes)")
                        except Exception as e:
                            logger.error(f"Error sending frame to Gemini: {e}")
                await asyncio.sleep(interval)

        async def receive_loop():
            async for response in session.receive():
                # Handle Tool Calls
                # Note: response.tool_call might contain multiple function_calls
                if hasattr(response, "tool_call") and response.tool_call:
                    for call in response.tool_call.function_calls:
                        if call.name == "request_deep_visual_analysis":
                            reason = call.args.get("reason", "Unknown")
                            focus = call.args.get("focus", "Unknown")
                            logger.info(f"Tool call received: request_deep_visual_analysis(reason='{reason}', focus='{focus}')")
                            
                            res = on_tool_call(reason, focus)
                            if asyncio.iscoroutine(res):
                                await res

                # Handle Text Responses
                if hasattr(response, "text") and response.text:
                    logger.debug(f"Vision text response: {response.text}")
                    res = on_text_response(response.text)
                    if asyncio.iscoroutine(res):
                        await res

        try:
            await asyncio.gather(send_loop(), receive_loop())
        except asyncio.CancelledError:
            logger.info("Vision channel loop cancelled.")
        except Exception as e:
            logger.exception(f"Unexpected error in vision channel loop: {e}")
        finally:
            logger.info("Vision channel session closed.")
