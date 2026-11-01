import base64
import re

import httpx

from src.config import settings


async def transcribe_with_fallback(
    data: bytes, filename: str, language: str | None
) -> tuple[str, str | None, str]:
    if settings.demo_mode and not settings.sarvam_api_key and not settings.groq_api_key:
        raise RuntimeError("Offline mode: use keyboard dictation")
    for name in (x.strip() for x in settings.stt_provider_order.split(",")):
        headers: dict[str, str] = {}
        if name == "local" and settings.local_stt_base_url:
            url = f"{settings.local_stt_base_url.rstrip('/')}/audio/transcriptions"
            values = {"model": settings.local_stt_model}
            if language:
                values["language"] = language
        elif name == "groq" and settings.groq_api_key:
            url = f"{settings.groq_base_url.rstrip('/')}/audio/transcriptions"
            headers = {"Authorization": f"Bearer {settings.groq_api_key.get_secret_value()}"}
            values = {"model": settings.groq_stt_model}
            if language:
                values["language"] = language
        elif name == "sarvam" and settings.sarvam_api_key:
            url = f"{settings.sarvam_base_url.rstrip('/')}/speech-to-text"
            headers = {"api-subscription-key": settings.sarvam_api_key.get_secret_value()}
            values = {
                "model": settings.sarvam_stt_model or "saaras:v3",
            }
            if language and language != "unknown":
                values["language_code"] = f"{language}-IN" if "-" not in language else language
        else:
            continue
        try:
            async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    files={"file": (filename, data, "application/octet-stream")},
                    data=values,
                )
                response.raise_for_status()
                payload = response.json()
                transcript = payload.get("transcript") if name == "sarvam" else payload.get("text")
                if not isinstance(transcript, str) or not transcript.strip():
                    raise ValueError("STT response contains no transcript")
                detected = payload.get("language_code") or payload.get("language") or language
                detected = {"Hindi": "hi", "hindi": "hi", "English": "en", "english": "en"}.get(
                    detected, detected
                )
                return transcript, detected.split("-")[0] if detected else None, name
        except (httpx.HTTPError, ValueError, KeyError):
            continue
    raise RuntimeError("No STT provider available; use keyboard dictation")


_MD_RE = re.compile(r"[*_`#>|]+|\[(?:[^\]]*)\]\([^)]*\)|^-{3,}$", re.MULTILINE)
_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]+")


def speakable(text: str, limit: int = 500) -> str:
    """Strip markdown / emoji so TTS reads the message, not its formatting."""
    clean = _EMOJI_RE.sub(" ", _MD_RE.sub(" ", text))
    clean = re.sub(r"^\s*(?:[•\-–]|\d+\.)\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    end = max(cut.rfind(". "), cut.rfind("। "), cut.rfind("? "))
    return cut[: end + 1] if end > limit // 2 else cut


async def synthesize_speech(
    text: str,
    language: str = "hi",
    speaker: str = "aditya",
) -> bytes:
    """Synthesizes text to spoken audio using Sarvam bulbul:v3 voice model."""
    if not settings.sarvam_api_key:
        raise RuntimeError("SARVAM_API_KEY is not configured")
    url = f"{settings.sarvam_base_url.rstrip('/')}/text-to-speech"
    headers = {
        "api-subscription-key": settings.sarvam_api_key.get_secret_value(),
        "Content-Type": "application/json",
    }
    lang_code = "hi-IN" if language and language.startswith("hi") else "en-IN"
    # Ensure speaker is valid for bulbul:v3
    valid_speakers = {"aditya", "ritu", "ashutosh", "priya", "neha", "rahul", "pooja", "rohan", "simran", "kavya"}
    chosen_speaker = speaker if speaker in valid_speakers else "aditya"

    payload = {
        "inputs": [speakable(text)],
        "target_language_code": lang_code,
        "speaker": chosen_speaker,
        "model": "bulbul:v3",
    }
    async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        audios = data.get("audios", [])
        if not audios:
            raise ValueError("No audio returned by Sarvam TTS")
        return base64.b64decode(audios[0])

