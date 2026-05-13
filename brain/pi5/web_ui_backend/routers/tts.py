from typing import Optional

from fastapi import File, UploadFile
from pydantic import BaseModel

from .. import core
from brain.config import BrainConfig
from brain.speech.chatterbox_client import (
    list_chatterbox_predefined_voices,
    list_chatterbox_reference_files,
    synthesize_with_chatterbox,
    upload_chatterbox_reference_audio,
)
from brain.speech.tts import synthesize_gemini_live_pcm
from brain.speech.voice_utils import edge_prosody, normalize_tts_text, pick_edge_voice

app = core.app


def _normalize_chatterbox_voice_mode(value: Optional[str]) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "clone":
        return "clone"
    return "predefined"


def _pcm_24000_to_wav_bytes(pcm: bytes) -> bytes:
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm)
    return buffer.getvalue()


class TTSRequest(BaseModel):
    text: str
    lang: str = "ar"
    voice: Optional[str] = None
    provider: Optional[str] = None
    baseUrl: Optional[str] = None
    voiceGender: Optional[str] = None
    rate: Optional[float] = None
    chatterboxVoiceMode: Optional[str] = None
    referenceAudio: Optional[str] = None


@app.post("/api/tts/speak")
async def tts_speak(body: TTSRequest):
    try:
        import base64

        settings = await core.load_settings()
        provider = str(body.provider or settings.ttsProvider or "edge").strip().lower()
        gender = str(body.voiceGender or settings.ttsVoiceGender or "female").strip().lower()
        language = body.lang or settings.ttsLang or settings.robotLanguage or "ar-EG"
        rate_value = float(body.rate) if isinstance(body.rate, (int, float)) else settings.ttsRate

        text = normalize_tts_text(body.text, language=language)
        if not text:
            return {"success": False, "error": "Text is empty after normalization", "format": "mp3"}

        if provider == "chatterbox":
            voice_mode = _normalize_chatterbox_voice_mode(body.chatterboxVoiceMode or settings.chatterboxVoiceMode)
            reference_audio = str(body.referenceAudio or settings.chatterboxReferenceAudio or "").strip()
            audio_data, output_format, metadata = await synthesize_with_chatterbox(
                text=text,
                base_url=body.baseUrl or settings.chatterboxBaseUrl,
                language=language,
                voice_gender=gender,
                voice_mode=voice_mode,
                reference_audio=reference_audio,
                voice_uri=body.voice or settings.ttsVoiceURI or "",
                speed_factor=rate_value,
                output_format="mp3",
            )
            return {
                "success": True,
                "audio": base64.b64encode(audio_data).decode("utf-8"),
                "format": output_format,
                "voice": metadata.get("voice"),
                "normalizedText": text,
                "provider": "chatterbox",
                "voiceMode": metadata.get("voiceMode"),
            }

        if provider == "gemini":
            cfg = BrainConfig.from_env()
            pcm_data = await synthesize_gemini_live_pcm(
                text=text,
                api_key=cfg.google_api_key,
                voice_gender=gender,
                model_id=cfg.gemini_live_model,
            )
            return {
                "success": True,
                "audio": base64.b64encode(_pcm_24000_to_wav_bytes(pcm_data)).decode("utf-8"),
                "format": "wav",
                "voice": "gemini-live",
                "normalizedText": text,
                "provider": "gemini",
            }

        import edge_tts

        if body.voice:
            voice = body.voice
        else:
            voice = pick_edge_voice(
                language=language,
                voice_gender=gender,
                explicit_voice=settings.ttsVoiceURI or "",
            )

        rate, pitch = edge_prosody(language=language, tts_rate=rate_value)

        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]

        return {
            "success": True,
            "audio": base64.b64encode(audio_data).decode("utf-8"),
            "format": "mp3",
            "voice": voice,
            "normalizedText": text,
            "provider": "edge",
        }
    except ImportError:
        return {"success": False, "error": "edge-tts not installed. Run: pip install edge-tts", "format": "mp3"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "format": "mp3"}


@app.get("/api/tts/voices")
async def tts_voices(provider: Optional[str] = None, baseUrl: Optional[str] = None):
    try:
        settings = await core.load_settings()
        selected_provider = str(provider or settings.ttsProvider or "edge").strip().lower()

        if selected_provider == "chatterbox":
            voices = await list_chatterbox_predefined_voices(baseUrl or settings.chatterboxBaseUrl)
            return {"success": True, "voices": voices, "provider": "chatterbox"}

        if selected_provider == "gemini":
            voices = [
                {"ShortName": "Kore", "FriendlyName": "Gemini Live Kore", "Gender": "Female", "Locale": "ar-XA"},
                {"ShortName": "Zephyr", "FriendlyName": "Gemini Live Zephyr", "Gender": "Female", "Locale": "ar-XA"},
                {"ShortName": "Charon", "FriendlyName": "Gemini Live Charon", "Gender": "Male", "Locale": "ar-XA"},
            ]
            return {"success": True, "voices": voices, "provider": "gemini"}

        import edge_tts

        voices = await edge_tts.list_voices()
        filtered = [voice for voice in voices if voice["Locale"].startswith("ar") or voice["Locale"].startswith("en")]
        return {"success": True, "voices": filtered, "provider": "edge"}
    except ImportError:
        return {"success": False, "error": "edge-tts not installed"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/api/tts/chatterbox/reference-files")
async def tts_chatterbox_reference_files(baseUrl: Optional[str] = None):
    try:
        settings = await core.load_settings()
        files = await list_chatterbox_reference_files(baseUrl or settings.chatterboxBaseUrl)
        return {"success": True, "files": sorted(files), "provider": "chatterbox"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "files": []}


@app.post("/api/tts/chatterbox/reference-files")
async def upload_tts_chatterbox_reference_files(
    files: list[UploadFile] = File(...),
    baseUrl: Optional[str] = None,
):
    try:
        settings = await core.load_settings()
        upload_payload: list[tuple[str, bytes, str]] = []
        for file_obj in files:
            filename = str(file_obj.filename or "").strip()
            if not filename:
                await file_obj.close()
                continue
            content = await file_obj.read()
            content_type = str(file_obj.content_type or "application/octet-stream")
            await file_obj.close()
            upload_payload.append((filename, content, content_type))

        if not upload_payload:
            return {"success": False, "error": "No valid audio files were provided.", "uploaded_files": []}

        payload = await upload_chatterbox_reference_audio(
            base_url=baseUrl or settings.chatterboxBaseUrl,
            files=upload_payload,
        )
        uploaded_files = payload.get("uploaded_files") if isinstance(payload, dict) else []
        errors = payload.get("errors") if isinstance(payload, dict) else []
        success = bool(uploaded_files) or not errors
        response = {
            "success": success,
            "provider": "chatterbox",
        }
        if isinstance(payload, dict):
            response.update(payload)
        return response
    except Exception as exc:
        return {"success": False, "error": str(exc), "uploaded_files": []}


class CoquiTTSRequest(BaseModel):
    text: str
    lang: str = "ar"
    speaker_wav: Optional[str] = None


_coqui_tts_model = None


@app.post("/api/tts/coqui")
async def coqui_tts_speak(body: CoquiTTSRequest):
    global _coqui_tts_model

    try:
        import base64
        import os
        import tempfile

        from TTS.api import TTS

        if _coqui_tts_model is None:
            _coqui_tts_model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file_obj:
            temp_path = file_obj.name

        try:
            if body.speaker_wav:
                _coqui_tts_model.tts_to_file(
                    text=body.text,
                    speaker_wav=body.speaker_wav,
                    language=body.lang,
                    file_path=temp_path,
                )
            else:
                _coqui_tts_model.tts_to_file(text=body.text, language=body.lang, file_path=temp_path)

            with open(temp_path, "rb") as file_obj:
                audio_data = file_obj.read()

            return {
                "success": True,
                "audio": base64.b64encode(audio_data).decode("utf-8"),
                "format": "wav",
                "model": "xtts_v2",
            }
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    except ImportError as exc:
        return {"success": False, "error": f"Coqui TTS not installed: {exc}", "format": "wav"}
    except Exception as exc:
        return {"success": False, "error": str(exc), "format": "wav"}
