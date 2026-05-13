from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

import pyaudio
from google import genai
from google.genai import types

from brain.speech.gemini_live_common import (
    DEFAULT_LIVE_MODEL,
    create_live_client,
    require_single_gemini_api_key,
    resolve_live_model,
)


logger = logging.getLogger(__name__)

AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
MIC_RATE = 16000
SPEAKER_RATE = 24000
CHUNK_SIZE = 512

@dataclass
class LiveAudioStreams:
    audio: pyaudio.PyAudio
    mic_stream: Any
    speaker_stream: Any


def pick_live_voice(voice_gender: str = "female", explicit_voice: str = "") -> str:
    explicit = str(explicit_voice or os.getenv("BRAIN_GEMINI_LIVE_VOICE", "")).strip()
    if explicit:
        return explicit
    return "Charon" if str(voice_gender or "").strip().lower() == "male" else "Kore"


def build_live_audio_config(
    *,
    system_instruction: str,
    voice_gender: str = "female",
    voice_name: str = "",
    input_transcription: bool = True,
    output_transcription: bool = False,
    tools: list[Any] | None = None,
) -> types.LiveConnectConfig:
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=pick_live_voice(voice_gender, voice_name)
            )
        )
    )
    compression = types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow())
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        speech_config=speech_config,
        input_audio_transcription=types.AudioTranscriptionConfig()
        if input_transcription
        else None,
        output_audio_transcription=types.AudioTranscriptionConfig() if output_transcription else None,
        context_window_compression=compression,
        system_instruction=types.Content(parts=[types.Part.from_text(text=system_instruction)]),
        tools=tools,
    )




def _device_name(audio: pyaudio.PyAudio, index: int | None) -> str:
    if index is None:
        return "default"
    try:
        info = audio.get_device_info_by_index(index)
        return f"{index}: {info.get('name', 'unknown')}"
    except Exception:
        return str(index)


def _iter_device_indexes(audio: pyaudio.PyAudio, *, input_device: bool) -> list[int | None]:
    candidates: list[int | None] = [None]
    count = audio.get_device_count()
    for index in range(count):
        try:
            info = audio.get_device_info_by_index(index)
        except Exception:
            continue
        max_channels = info.get("maxInputChannels" if input_device else "maxOutputChannels", 0)
        try:
            if int(max_channels) > 0:
                candidates.append(index)
        except Exception:
            continue
    return candidates


def _resolve_device_hint(audio: pyaudio.PyAudio, hint: str, *, input_device: bool) -> int | None:
    value = str(hint or "").strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)

    needle = value.lower()
    count = audio.get_device_count()
    channel_key = "maxInputChannels" if input_device else "maxOutputChannels"
    for index in range(count):
        try:
            info = audio.get_device_info_by_index(index)
        except Exception:
            continue
        if int(info.get(channel_key, 0) or 0) <= 0:
            continue
        if needle in str(info.get("name", "")).lower():
            return index
    raise RuntimeError(f"Audio device hint '{hint}' did not match any usable device.")


def _open_stream(
    audio: pyaudio.PyAudio,
    *,
    input_device: bool,
    sample_rate: int,
    chunk_size: int,
    device_hint: str = "",
) -> Any:
    explicit_index = _resolve_device_hint(audio, device_hint, input_device=input_device) if device_hint else None
    candidates = [explicit_index] if explicit_index is not None else _iter_device_indexes(audio, input_device=input_device)
    errors: list[str] = []

    for index in candidates:
        try:
            kwargs: dict[str, Any] = {
                "format": AUDIO_FORMAT,
                "channels": AUDIO_CHANNELS,
                "rate": sample_rate,
                "frames_per_buffer": chunk_size,
            }
            if input_device:
                kwargs["input"] = True
                if index is not None:
                    kwargs["input_device_index"] = index
            else:
                kwargs["output"] = True
                if index is not None:
                    kwargs["output_device_index"] = index

            stream = audio.open(**kwargs)
            kind = "mic" if input_device else "speaker"
            logger.info("Gemini Live %s stream opened on %s at %s Hz", kind, _device_name(audio, index), sample_rate)
            return stream
        except Exception as exc:
            errors.append(f"{_device_name(audio, index)} -> {type(exc).__name__}: {exc}")

    direction = "input" if input_device else "output"
    available = describe_audio_devices(audio)
    details = "\n".join(errors[-8:])
    raise RuntimeError(f"Could not open any {direction} audio device at {sample_rate} Hz.\n{details}\n{available}")


def open_live_audio_streams(
    *,
    mic_rate: int = MIC_RATE,
    speaker_rate: int = SPEAKER_RATE,
    chunk_size: int = CHUNK_SIZE,
    mic_device: str = "",
    speaker_device: str = "",
) -> LiveAudioStreams:
    audio = pyaudio.PyAudio()
    mic = None
    speaker = None
    try:
        mic = _open_stream(
            audio,
            input_device=True,
            sample_rate=mic_rate,
            chunk_size=chunk_size,
            device_hint=mic_device or os.getenv("BRAIN_MIC_DEVICE", ""),
        )
        speaker = _open_stream(
            audio,
            input_device=False,
            sample_rate=speaker_rate,
            chunk_size=chunk_size,
            device_hint=speaker_device or os.getenv("BRAIN_SPEAKER_DEVICE", ""),
        )
        return LiveAudioStreams(audio=audio, mic_stream=mic, speaker_stream=speaker)
    except Exception:
        for stream in (mic, speaker):
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    logger.exception("Failed to close partially opened audio stream")
        audio.terminate()
        raise


def close_live_audio_streams(streams: LiveAudioStreams) -> None:
    for stream in (streams.mic_stream, streams.speaker_stream):
        try:
            stream.stop_stream()
        except Exception:
            logger.exception("Failed to stop audio stream")
        try:
            stream.close()
        except Exception:
            logger.exception("Failed to close audio stream")
    try:
        streams.audio.terminate()
    except Exception:
        logger.exception("Failed to terminate PyAudio")


def describe_audio_devices(audio: pyaudio.PyAudio | None = None) -> str:
    owns_audio = audio is None
    audio = audio or pyaudio.PyAudio()
    try:
        lines = ["Available audio devices:"]
        for index in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(index)
            except Exception as exc:
                lines.append(f"- {index}: unreadable ({exc})")
                continue
            lines.append(
                "- {index}: {name} | in={inp} out={out} default_rate={rate}".format(
                    index=index,
                    name=info.get("name", "unknown"),
                    inp=info.get("maxInputChannels", 0),
                    out=info.get("maxOutputChannels", 0),
                    rate=info.get("defaultSampleRate", "?"),
                )
            )
        return "\n".join(lines)
    finally:
        if owns_audio:
            audio.terminate()


async def send_mic_to_gemini(session: Any, mic_stream: Any, *, chunk_size: int = CHUNK_SIZE) -> None:
    while True:
        data = await asyncio.to_thread(mic_stream.read, chunk_size, exception_on_overflow=False)
        await session.send_realtime_input(
            audio=types.Blob(data=data, mime_type=f"audio/pcm;rate={MIC_RATE}")
        )
        await asyncio.sleep(0.01)


async def play_gemini_audio(speaker_stream: Any, audio_bytes: bytes) -> None:
    if audio_bytes:
        await asyncio.to_thread(speaker_stream.write, audio_bytes)


async def send_text_turn(session: Any, text: str) -> None:
    await session.send_client_content(
        turns=types.Content(role="user", parts=[types.Part.from_text(text=text)]),
        turn_complete=True,
    )


def flush_speaker_stream(speaker_stream: Any) -> None:
    """Immediately stop and restart the stream to clear the buffer (barge-in)."""
    try:
        if speaker_stream.is_active():
            speaker_stream.stop_stream()
            speaker_stream.start_stream()
            logger.info("🔊 Audio buffer flushed (Barge-in detected)")
    except Exception as e:
        logger.error(f"Failed to flush speaker stream: {e}")
