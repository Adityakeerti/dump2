from unittest.mock import AsyncMock

import httpx
import pytest

from src.config import settings
from src.providers import registry, speech
from src.providers.base import GeneratedText
from src.providers.hosted import OpenAICompatibleProvider, mask_pii


@pytest.fixture(autouse=True)
def reset_circuits():
    registry._requests.clear()
    registry._cooldown.clear()
    registry._failures.clear()


async def test_429_immediately_fails_over(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "provider_order", "local,groq")
    request = httpx.Request("POST", "http://provider.invalid/chat/completions")
    failed = AsyncMock()
    failed.generate.side_effect = httpx.HTTPStatusError(
        "limited", request=request, response=httpx.Response(429, request=request)
    )
    good = AsyncMock()
    good.generate.return_value = GeneratedText("supported", "groq")
    monkeypatch.setattr(registry, "configured_providers", lambda: {"local": failed, "groq": good})
    result = await registry.generate_with_failover(
        system="", user="", context=["evidence"], language="en"
    )
    assert result.provider == "groq"
    assert failed.generate.await_count == 1


async def test_timeout_retries_once_then_falls_over(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "provider_order", "local,groq")
    failed = AsyncMock()
    failed.generate.side_effect = httpx.ReadTimeout("timeout")
    good = AsyncMock()
    good.generate.return_value = GeneratedText("supported", "groq")
    monkeypatch.setattr(registry, "configured_providers", lambda: {"local": failed, "groq": good})
    assert (
        await registry.generate_with_failover(system="", user="", context=[], language="en")
    ).provider == "groq"
    assert failed.generate.await_count == 2


async def test_all_down_and_offline_paths(monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(registry, "configured_providers", lambda: {})
    with pytest.raises(RuntimeError):
        await registry.generate_with_failover(system="", user="", context=[], language="en")
    monkeypatch.setattr(settings, "demo_mode", True)
    answer = await registry.generate_with_failover(
        system="", user="", context=["verified passage"], language="en"
    )
    assert answer.fallback
    assert "verified passage" in answer.text


def test_hosted_pii_mask():
    masked = mask_pii("Email alice@example.com or phone +91 99999 00000")
    assert "alice@example.com" not in masked
    assert "99999" not in masked


async def test_openai_protocol_and_invalid_result(monkeypatch):
    real_client = httpx.AsyncClient
    captured = []

    def handle(request):
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    result = await OpenAICompatibleProvider(
        "local", "http://local.invalid/v1", None, "model"
    ).generate(system="rules", user="q", context=["source"], language="en")
    assert result.text == "answer"
    assert str(captured[0].url) == "http://local.invalid/v1/chat/completions"


async def test_speech_local_fallback_to_groq(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "local_stt_base_url", "http://local.invalid/v1")
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("fake-test-key"))
    real_client = httpx.AsyncClient

    def handle(request):
        if request.url.host == "local.invalid":
            return httpx.Response(503)
        return httpx.Response(200, json={"text": "नमस्ते", "language": "hi"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    text, language, provider = await speech.transcribe_with_fallback(
        b"audio", "recording.wav", "hi"
    )
    assert (text, language, provider) == ("नमस्ते", "hi", "groq")
