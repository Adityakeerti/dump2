"""Live Integration tests for Sarvam AI Voice & STT."""

import os
import pytest
from src.config import settings
from src.providers import speech


@pytest.mark.asyncio
async def test_sarvam_tts_synthesis():
    """Verify Sarvam Text-to-Speech produces playable audio with bulbul:v3."""
    if not settings.sarvam_api_key:
        pytest.skip("SARVAM_API_KEY not configured")

    hindi_text = "नमस्ते, यह सिटी सेंस का ध्वनि परीक्षण है।"
    audio_bytes = await speech.synthesize_speech(hindi_text, language="hi", speaker="aditya")

    assert audio_bytes is not None
    assert len(audio_bytes) > 1000  # valid WAV header and audio payload
    assert audio_bytes[:4] == b"RIFF"  # standard WAV file header


@pytest.mark.asyncio
async def test_sarvam_stt_transcription(monkeypatch):
    """Verify Sarvam Speech-to-Text transcribes speech with saaras:v3."""
    if not settings.sarvam_api_key:
        pytest.skip("SARVAM_API_KEY not configured")

    monkeypatch.setattr(settings, "stt_provider_order", "sarvam")
    # Generate a short speech clip first
    audio_bytes = await speech.synthesize_speech("नमस्ते", language="hi", speaker="aditya")

    transcript, lang, provider = await speech.transcribe_with_fallback(
        audio_bytes, "test.wav", "hi"
    )

    assert transcript is not None
    assert len(transcript.strip()) > 0
    assert provider == "sarvam"
