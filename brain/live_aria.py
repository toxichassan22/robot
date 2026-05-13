from __future__ import annotations

import asyncio
import logging

from brain.config import BrainConfig
from brain.speech.gemini_live_audio import (
    build_live_audio_config,
    close_live_audio_streams,
    create_live_client,
    open_live_audio_streams,
    play_gemini_audio,
    resolve_live_model,
    send_mic_to_gemini,
)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("Aria.Live")


async def main() -> None:
    cfg = BrainConfig.from_env()
    client = create_live_client(cfg.google_api_key)
    model_id = resolve_live_model(cfg.gemini_live_model)
    streams = open_live_audio_streams()

    config = build_live_audio_config(
        system_instruction=(
            "أنتِ أريا، مساعدة ذكية مصرية. اسمعي صوت المستخدم مباشرة من المايك وردي بصوتك مباشرة. "
            "اتكلمي باللهجة المصرية فقط، وخلي إجاباتك قصيرة وسريعة كأننا في مكالمة تليفون."
        ),
        voice_gender=cfg.tts_voice_gender,
        input_transcription=True,
        output_transcription=True,
    )

    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            logger.info("Gemini Live connected with model %s. Speak into the mic.", model_id)

            async def receive_from_gemini() -> None:
                async for response in session.receive():
                    server_content = response.server_content
                    if server_content and server_content.input_transcription:
                        text = (server_content.input_transcription.text or "").strip()
                        if text:
                            logger.info("Gemini heard: %s", text)
                    if server_content and server_content.output_transcription:
                        text = (server_content.output_transcription.text or "").strip()
                        if text:
                            logger.info("Gemini said: %s", text)

                    if server_content and server_content.model_turn:
                        for part in server_content.model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await play_gemini_audio(streams.speaker_stream, part.inline_data.data)

            await asyncio.gather(
                send_mic_to_gemini(session, streams.mic_stream),
                receive_from_gemini(),
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Gemini Live session failed")
        raise
    finally:
        close_live_audio_streams(streams)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSystem shutdown.")
