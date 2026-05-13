import asyncio
import logging

from brain.debate_engine import DebateEngine
from brain.models import deepseek
from brain.memory.context_manager import context_manager
from brain.memory.sqlite_memory import SqliteMemory
from brain.memory.chat_archiver import ChatArchiver
from brain.perception.perceiver import UnifiedPerceiver
from brain.config import BrainConfig
from brain.speech.gemini_live_audio import (
    build_live_audio_config,
    close_live_audio_streams,
    create_live_client,
    open_live_audio_streams,
    play_gemini_audio,
    resolve_live_model,
    send_mic_to_gemini,
    send_text_turn,
    flush_speaker_stream,
)

logger = logging.getLogger("Senses.EarsMouth")

# Initialize core system components
cfg = BrainConfig.from_env()
memory = SqliteMemory(path="./config/data/brain_memory.db")
archiver = ChatArchiver(memory, cfg)
perceiver = UnifiedPerceiver(cfg)
debate_engine = DebateEngine()

async def process_query_in_background(complexity: str, user_text: str, session):
    if complexity == "auto":
        word_count = len(str(user_text or "").split())
        complex_keywords = ("بحث", "حلل", "قارن", "برمجة", "كود", "خطة", "دراسة", "اشرح بالتفصيل", "قصة", "احكي", "تكلم")
        complexity = "complex" if word_count > 15 or any(k in user_text for k in complex_keywords) else "simple"

    # 1. Store user message in long-term memory
    await memory.append_short_term(role="user", content=user_text)
    
    # 2. Check for "Reading" request (High-res OCR)
    vision_desc = ""
    reading_keywords = ["اقرا", "اقرأ", "مكتوب", "روشتة", "صورة", "شوف", "ورقة", "خط", "read", "what is written"]
    if any(kw in user_text.lower() for kw in reading_keywords):
        logger.info("🔍 Voice request for reading detected! Taking high-res snapshot...")
        custom_prompt = f"The user asked: '{user_text}'. Read the text in the image exactly as it is written. Translate it if necessary. If it's a medical prescription, be precise."
        # Use our new blocking describe_now feature
        vision_desc = await asyncio.to_thread(perceiver.describe_now, custom_prompt)
    
    # 3. Get generic vision context if not in reading mode
    if not vision_desc:
        vision_desc = context_manager.get_vision_context_json()
    
    # 4. Fetch recent conversation history for context
    history = await memory.get_recent_short_term(limit=10)
    history_text = "\n".join([f"{m['role'].capitalize()}: {m['content']}" for m in history])

    # 5. Route and generate response
    if complexity == "simple":
        logger.info("⚡ FAST PATH: Sending directly to DeepSeek with context...")
        prompt = (
            f"Conversation History:\n{history_text}\n\n"
            f"Vision State: {vision_desc}\n"
            f"User currently said: {user_text}"
        )
        system_prompt = (
            "You are Aria, an Egyptian robot. Respond with appropriate length based on the user request. "
            "If the user asks for a story, tell a creative and engaging one. "
            "Use the provided conversation history to maintain context. "
            "IMPORTANT: Use Arabic diacritics (tashkeel) on difficult or ambiguous words to ensure the TTS engine pronounces them correctly. "
        )
        final_response = await deepseek.generate(prompt, system_prompt)
    else:
        logger.info("🧠 COMPLEX PATH: Starting Debate with context...")
        # We should also pass history to debate_engine if needed, 
        # but let's start with the simple path fix first.
        final_response = await debate_engine.start_debate(user_text, vision_desc)
        
        # Clean XML tags if present
        if "<spoken_response>" in final_response:
            final_response = final_response.split("<spoken_response>")[1].split("</spoken_response>")[0].strip()

    # 5. Store response in memory and check for compression (30M limit)
    await memory.append_short_term(role="assistant", content=final_response)
    asyncio.create_task(archiver.check_and_compress())

    print(f"\n[ARIA]: {final_response}\n", flush=True)
    await send_text_turn(session, f"SPEAK: {final_response}")

async def start_ears_and_mouth():
    logger.info("🔄 جاري الاتصال بعقل أريا اللايف...")
    
    live_cfg = BrainConfig.from_env()
    client = create_live_client(live_cfg.google_api_key)
    streams = open_live_audio_streams()
    model_id = resolve_live_model(live_cfg.gemini_live_model)

    config = build_live_audio_config(
        system_instruction=(
            "أنتِ أريا، واجهة الصوت الحي. اسمعي صوت المستخدم من المايك وقدمي تفريغ الكلام للنظام. "
            "لا تردي على كلام المايك بنفسك. عندما يصلك نص يبدأ بـ SPEAK: انطقي النص الذي بعد العلامة حرفياً "
            "باللهجة المصرية وبدون أي إضافة."
        ),
        voice_gender=live_cfg.tts_voice_gender,
        input_transcription=True,
        output_transcription=True,
    )

    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            logger.info("🎙️ الخط اتفتح! أريا سامعاك من Gemini Live مباشرة.")
            transcript_parts: list[str] = []
            background_tasks: set[asyncio.Task] = set()

            def track_task(task: asyncio.Task) -> None:
                background_tasks.add(task)

                def done_callback(done: asyncio.Task) -> None:
                    background_tasks.discard(done)
                    try:
                        done.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        logger.exception("Background voice processing failed")

                task.add_done_callback(done_callback)

            async def receive_from_gemini():
                async for response in session.receive():
                    server_content = response.server_content
                    if not server_content:
                        continue

                    transcription = server_content.input_transcription
                    if transcription:
                        # BARGE-IN: If we get any transcription text, the user is talking.
                        # We flush the speaker to stop the robot's current chatter.
                        text = (transcription.text or "").strip()
                        if text:
                            flush_speaker_stream(streams.speaker_stream)
                            transcript_parts.append(text)
                        if transcription.finished:
                            user_text = " ".join(part for part in transcript_parts if part).strip()
                            transcript_parts.clear()
                            if user_text and not user_text.startswith("SPEAK:"):
                                print(f"\n[USER]: {user_text}", flush=True)
                                track_task(
                                    asyncio.create_task(
                                        process_query_in_background("auto", user_text, session)
                                    )
                                )

                    output_transcription = server_content.output_transcription
                    if output_transcription and output_transcription.text:
                        logger.info("Gemini said: %s", output_transcription.text.strip())

                    model_turn = server_content.model_turn
                    if model_turn is not None:
                        for part in model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                await play_gemini_audio(streams.speaker_stream, part.inline_data.data)

            try:
                await asyncio.gather(
                    send_mic_to_gemini(session, streams.mic_stream),
                    receive_from_gemini(),
                )
            finally:
                for task in background_tasks:
                    task.cancel()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Gemini Live ears/mouth session failed")
        raise
    finally:
        close_live_audio_streams(streams)
