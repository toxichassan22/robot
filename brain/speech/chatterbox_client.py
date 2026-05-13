from __future__ import annotations

from typing import Any

import httpx


DEFAULT_CHATTERBOX_BASE_URL = "http://127.0.0.1:8004"


def normalize_chatterbox_base_url(value: str | None) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return DEFAULT_CHATTERBOX_BASE_URL
    return candidate.rstrip("/")


def normalize_chatterbox_voice_mode(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate == "clone":
        return "clone"
    return "predefined"


def default_chatterbox_voice(voice_gender: str = "female") -> str:
    gender = str(voice_gender or "").strip().lower()
    if gender == "male":
        return "Michael.wav"
    return "Layla.wav"


def select_chatterbox_voice(*, voice_gender: str = "female", explicit_voice: str = "") -> str:
    candidate = str(explicit_voice or "").strip()
    if candidate:
        return candidate
    return default_chatterbox_voice(voice_gender)


def _audio_format_from_content_type(content_type: str | None, fallback: str = "mp3") -> str:
    value = str(content_type or "").strip().lower()
    if "wav" in value:
        return "wav"
    if "opus" in value or "ogg" in value:
        return "opus"
    if "mpeg" in value or "mp3" in value:
        return "mp3"
    return fallback


def normalize_chatterbox_language(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return "ar"
    candidate = candidate.replace("_", "-")
    base = candidate.split("-", 1)[0].strip()
    return base or "ar"


async def _ensure_multilingual_model_ready(
    *, client: httpx.AsyncClient, root: str, language: str
) -> None:
    if language == "en":
        return

    response = await client.post(f"{root}/load_multilingual_model")
    response.raise_for_status()


async def probe_chatterbox(base_url: str | None) -> dict[str, Any]:
    root = normalize_chatterbox_base_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{root}/health")
        response.raise_for_status()
        payload = response.json()
        return {
            "configured": True,
            "supported": True,
            "ready": bool(payload.get("ready", True)),
            "reachable": True,
            "degraded": not bool(payload.get("ready", True)),
            "message": str(payload.get("message") or "Chatterbox reachable"),
            "baseUrl": root,
        }
    except Exception:
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                response = await client.get(f"{root}/get_predefined_voices")
            response.raise_for_status()
            return {
                "configured": True,
                "supported": True,
                "ready": True,
                "reachable": True,
                "degraded": False,
                "message": "Chatterbox reachable",
                "baseUrl": root,
            }
        except Exception as exc:
            return {
                "configured": True,
                "supported": True,
                "ready": False,
                "reachable": False,
                "degraded": True,
                "message": f"Chatterbox unreachable: {exc}",
                "baseUrl": root,
            }


async def list_chatterbox_predefined_voices(base_url: str | None) -> list[dict[str, Any]]:
    root = normalize_chatterbox_base_url(base_url)
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{root}/get_predefined_voices")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []

    voices: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or item.get("id") or "").strip()
        if not filename:
            continue
        display_name = str(item.get("display_name") or filename).strip()
        voices.append(
            {
                "ShortName": filename,
                "FriendlyName": display_name,
                "Gender": None,
                "Locale": None,
                "Provider": "chatterbox",
            }
        )
    return voices


async def list_chatterbox_reference_files(base_url: str | None) -> list[str]:
    root = normalize_chatterbox_base_url(base_url)
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{root}/get_reference_files")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []

    files: list[str] = []
    for item in payload:
        name = str(item or "").strip()
        if name:
            files.append(name)
    return files


async def upload_chatterbox_reference_audio(
    *,
    base_url: str | None,
    files: list[tuple[str, bytes, str]],
) -> dict[str, Any]:
    root = normalize_chatterbox_base_url(base_url)
    upload_files = [
        (
            "files",
            (
                str(filename).strip(),
                content,
                str(content_type or "application/octet-stream").strip() or "application/octet-stream",
            ),
        )
        for filename, content, content_type in files
        if str(filename or "").strip()
    ]
    if not upload_files:
        return {
            "message": "No valid files to upload.",
            "uploaded_files": [],
            "all_reference_files": [],
            "errors": [{"filename": "Unknown", "error": "No valid files to upload."}],
        }

    timeout = httpx.Timeout(120.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{root}/upload_reference", files=upload_files)
    payload = response.json()
    if isinstance(payload, dict):
        payload.setdefault("status_code", response.status_code)
        return payload
    response.raise_for_status()
    return {}


async def synthesize_with_chatterbox(
    *,
    text: str,
    base_url: str | None,
    language: str,
    voice_gender: str = "female",
    voice_mode: str = "predefined",
    reference_audio: str = "",
    voice_uri: str = "",
    speed_factor: float = 1.0,
    output_format: str = "mp3",
) -> tuple[bytes, str, dict[str, Any]]:
    root = normalize_chatterbox_base_url(base_url)
    normalized_language = normalize_chatterbox_language(language)
    normalized_voice_mode = normalize_chatterbox_voice_mode(voice_mode)
    selected_reference = str(reference_audio or "").strip()
    selected_voice = select_chatterbox_voice(voice_gender=voice_gender, explicit_voice=voice_uri)
    effective_voice_mode = "clone" if normalized_voice_mode == "clone" and selected_reference else "predefined"
    payload: dict[str, Any] = {
        "text": text,
        "language": normalized_language,
        "voice_mode": effective_voice_mode,
        "output_format": output_format,
        "speed_factor": speed_factor,
        "split_text": True,
    }
    if effective_voice_mode == "clone":
        payload["reference_audio_filename"] = selected_reference
    else:
        payload["predefined_voice_id"] = selected_voice

    timeout = httpx.Timeout(240.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        await _ensure_multilingual_model_ready(
            client=client,
            root=root,
            language=normalized_language,
        )
        response = await client.post(f"{root}/tts", json=payload)
    response.raise_for_status()
    fmt = _audio_format_from_content_type(response.headers.get("content-type"), fallback=output_format)
    return response.content, fmt, {
        "voice": selected_reference if effective_voice_mode == "clone" else selected_voice,
        "baseUrl": root,
        "language": normalized_language,
        "voiceMode": effective_voice_mode,
        "referenceAudio": selected_reference if effective_voice_mode == "clone" else "",
    }
