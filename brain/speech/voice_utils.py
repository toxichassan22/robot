from __future__ import annotations

import re


_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_ARABIC_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")


def is_arabic_text(text: str) -> bool:
    return bool(_ARABIC_CHAR_RE.search(str(text or "")))


def pick_edge_voice(*, language: str, voice_gender: str, explicit_voice: str = "") -> str:
    explicit = str(explicit_voice or "").strip()
    if explicit:
        return explicit

    lang = str(language or "ar-EG").strip().lower()
    gender = str(voice_gender or "female").strip().lower()

    if lang.startswith("ar"):
        return "ar-EG-ShakirNeural" if gender == "male" else "ar-EG-SalmaNeural"
    return "en-US-ChristopherNeural" if gender == "male" else "en-US-JennyNeural"


def edge_prosody(*, language: str, tts_rate: float = 1.0) -> tuple[str, str]:
    lang = str(language or "").strip().lower()
    try:
        rate_factor = float(tts_rate)
    except Exception:
        rate_factor = 1.0
    rate_factor = min(max(rate_factor, 0.6), 1.5)

    if lang.startswith("ar"):
        base_rate = -10
        pitch = "-2Hz"
    else:
        base_rate = -4
        pitch = "+0Hz"

    adjusted_rate = base_rate + round((rate_factor - 1.0) * 40)
    return (_format_percent(adjusted_rate), pitch)


def normalize_tts_text(text: str, *, language: str = "ar-EG") -> str:
    value = str(text or "").strip()
    if not value:
        return ""

    value = _ARABIC_DIACRITICS_RE.sub("", value)
    value = value.replace("\r", "\n")
    value = re.sub(r"https?://\S+", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"www\.\S+", " ", value, flags=re.IGNORECASE)

    # Handle math operations and decimals before removing special chars
    value = re.sub(r"(\d+)\.(\d+)", r"\1 فاصل \2", value)
    while re.search(r"(\d+)\s*\*\s*(\d+)", value):
        value = re.sub(r"(\d+)\s*\*\s*(\d+)", r"\1 في \2", value)
    while re.search(r"(\d+)\s*/\s*(\d+)", value):
        value = re.sub(r"(\d+)\s*/\s*(\d+)", r"\1 على \2", value)
    while re.search(r"(\d+)\s*-\s*(\d+)", value):
        value = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1 ناقص \2", value)

    value = re.sub(r"[`*_~]+", " ", value)
    value = value.replace("&", " و ")
    value = value.replace("@", " ")
    value = value.replace("#", " ")
    value = value.replace("°C", " درجة مئوية ")
    value = value.replace("°", " درجة ")
    value = value.replace("%", " في المية ")
    value = value.replace("+", " زائد ")
    value = value.replace("=", " يساوي ")
    value = value.replace("\n", ". ")

    if str(language or "").strip().lower().startswith("ar") or is_arabic_text(value):
        replacements = {
            "AI": " الذكاء الاصطناعي ",
            "LLM": " موديل اللغة ",
            "VLM": " موديل الرؤية ",
            "GPU": " جي بي يو ",
            "CPU": " سي بي يو ",
            "RAM": " رام ",
            "VRAM": " في رام ",
            "USB": " يو إس بي ",
            "Wi-Fi": " واي فاي ",
            "wifi": " واي فاي ",
            "JSON": " جيسون ",
            "HTTP": " إتش تي تي بي ",
            "HTTPS": " إتش تي تي بي إس ",
            "API": " أي بي آي ",
        }
        for key, replacement in replacements.items():
            value = re.sub(rf"\b{re.escape(key)}\b", replacement, value, flags=re.IGNORECASE)

        value = _repair_underscored_arabic(value)
        value = value.replace("،", ". ")
        value = re.sub(r"[؛;:]+", ". ", value)
        value = re.sub(r"[!?؟]+", ". ", value)

    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\.\s*\.", ". ", value)
    return value.strip(" .")


def _repair_underscored_arabic(text: str) -> str:
    def fix_token(match: re.Match[str]) -> str:
        token = match.group(0)
        parts = [part for part in token.split("_") if part]
        if len(parts) >= 3:
            return "".join(parts)
        return " ".join(parts)

    return re.sub(r"[\u0600-\u06FF]+(?:_[\u0600-\u06FF]+)+", fix_token, text)


def _format_percent(value: int) -> str:
    return f"+{value}%" if value >= 0 else f"{value}%"
