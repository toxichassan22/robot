from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import tempfile
import time


async def speak(
    text: str,
    provider: str = "none",
    *,
    lang: str | None = None,
    gender: str | None = None,
    cache_dir: str | None = None,
    voice_model: str | None = None,
) -> None:
    if provider == "none":
        return
    if provider == "pyttsx3":
        await asyncio.to_thread(_pyttsx3_speak, text)
        return
    if provider == "gtts":
        await asyncio.to_thread(_gtts_speak, text, lang, gender, cache_dir)
        return
    if provider == "coqui":
        await asyncio.to_thread(_coqui_speak, text, lang, voice_model, cache_dir)
        return
    raise ValueError(f"Unknown TTS provider: {provider}")


def _pyttsx3_speak(text: str) -> None:
    try:
        import pyttsx3  # type: ignore
    except Exception as e:
        raise RuntimeError("pyttsx3 is required for TTS") from e
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _ensure_dir(p: str) -> str:
    d = os.path.abspath(p)
    os.makedirs(d, exist_ok=True)
    return d


def _play_mp3(path: str) -> None:
    if sys.platform.startswith("win"):
        import ctypes

        winmm = ctypes.WinDLL("winmm")
        cmd = f'open "{path}" type mpegvideo alias tts_mp3'
        winmm.mciSendStringW(cmd, None, 0, None)
        winmm.mciSendStringW("play tts_mp3 wait", None, 0, None)
        winmm.mciSendStringW("close tts_mp3", None, 0, None)
        return
    import subprocess

    subprocess.run(["mpg123", "-q", path], check=True)


def _play_wav(path: str) -> None:
    if sys.platform.startswith("win"):
        import winsound

        winsound.PlaySound(path, winsound.SND_FILENAME)
        return
    import subprocess

    subprocess.run(["aplay", "-q", path], check=True)


def _gtts_speak(text: str, lang: str | None, gender: str | None, cache_dir: str | None) -> None:
    try:
        from gtts import gTTS  # type: ignore
    except Exception as e:
        raise RuntimeError("gtts is required for gTTS TTS") from e

    language = (lang or os.getenv("BRAIN_ROBOT_LANGUAGE", "ar-EG")).strip() or "ar-EG"
    language = language.split("-")[0].lower()
    g = (gender or os.getenv("BRAIN_TTS_VOICE_GENDER", "female")).strip().lower() or "female"

    cache_root = _ensure_dir(cache_dir or os.getenv("BRAIN_TTS_CACHE_DIR", "./data/tts_cache"))
    key = _stable_hash(f"gtts|{language}|{g}|{text.strip()}")
    out_path = os.path.join(cache_root, f"{key}.mp3")
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        tmp = os.path.join(cache_root, f".tmp-{key}-{int(time.time()*1000)}.mp3")
        tts = gTTS(text=text, lang=language)
        tts.save(tmp)
        os.replace(tmp, out_path)
    _play_mp3(out_path)


def _coqui_speak(text: str, lang: str | None, voice_model: str | None, cache_dir: str | None) -> None:
    try:
        from TTS.api import TTS as CoquiTTS  # type: ignore
    except Exception as e:
        raise RuntimeError("TTS (Coqui) is required for coqui provider") from e

    cache_root = _ensure_dir(cache_dir or os.getenv("BRAIN_TTS_CACHE_DIR", "./data/tts_cache"))
    model = (voice_model or os.getenv("BRAIN_COQUI_VOICE_MODEL", "")).strip()
    if not model:
        model = "tts_models/en/ljspeech/tacotron2-DDC"

    key = _stable_hash(f"coqui|{model}|{lang or ''}|{text.strip()}")
    out_path = os.path.join(cache_root, f"{key}.wav")
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        tmp_dir = tempfile.mkdtemp(prefix="coqui-tts-")
        tmp_path = os.path.join(tmp_dir, f"{key}.wav")
        tts = CoquiTTS(model_name=model)
        tts.tts_to_file(text=text, file_path=tmp_path)
        os.replace(tmp_path, out_path)
    _play_wav(out_path)
