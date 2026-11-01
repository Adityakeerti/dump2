import json
import re

import httpx

from src.config import settings
from src.providers.base import GeneratedText


def mask_pii(value: str) -> str:
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", value)
    return re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "[phone]", value)


class OpenAICompatibleProvider:
    def __init__(self, name: str, base_url: str, api_key: str | None, model: str) -> None:
        self.name, self.base_url, self.api_key, self.model = name, base_url, api_key, model

    async def generate(
        self,
        *,
        system: str,
        user: str,
        context: list[str],
        language: str | None,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
    ) -> GeneratedText:
        if context:
            instruction = (
                "You are City Sense, the official civic AI assistant for Dehradun Nagar Nigam. "
                "Synthesize helpful, accurate, and articulate answers for citizens. "
                "Base specific municipal rules, categories, and procedures on the verified context below. "
                f"Respond in {'Hindi' if language == 'hi' else 'English'}.\n\n"
                f"VERIFIED MUNICIPAL CONTEXT:\n{json.dumps(context, ensure_ascii=False)}\n\n"
                f"{system}"
            )
        else:
            instruction = (
                "You are City Sense, the official civic AI assistant for Dehradun Nagar Nigam. "
                "Assist citizens warmly and professionally with reporting issues, civic inquiries, and city guidance. "
                f"Respond in {'Hindi' if language == 'hi' else 'English'}.\n\n"
                f"{system}"
            )

        messages = [
            {"role": "system", "content": instruction},
        ]
        messages.extend(history or [{"role": "user", "content": user}])
        if self.name != "local":
            messages = [
                {
                    **m,
                    **(
                        {"content": mask_pii(m["content"])}
                        if isinstance(m.get("content"), str)
                        else {}
                    ),
                }
                for m in messages
            ]
        payload = {
            "model": self.model,
            "temperature": 0.01,
            "max_tokens": 1024,
            "messages": messages,
        }
        if tools and (self.name != "local" or settings.local_tools_enabled):
            payload["tools"] = tools
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if self.name == "sarvam" and self.api_key:
            headers["api-subscription-key"] = self.api_key
        async with httpx.AsyncClient(timeout=settings.provider_timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}/chat/completions", headers=headers, json=payload
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            content = message.get("content") or ""
            calls = message.get("tool_calls") or []
            if len(json.dumps(calls)) > 32000:
                raise ValueError("Tool arguments exceed configured processing limit")
            if (
                not isinstance(content, str)
                or not isinstance(calls, list)
                or (not content.strip() and not calls)
            ):
                raise ValueError("Invalid model response")
            if len(calls) > 3 or any(
                not isinstance(call, dict)
                or not isinstance(call.get("function"), dict)
                or not isinstance(call.get("id"), str)
                or not isinstance(call["function"].get("name"), str)
                for call in calls
            ):
                raise ValueError("Invalid or excessive tool calls")
            if len(content) > settings.max_provider_answer_chars:
                raise ValueError("Model response exceeds configured limit")
            return GeneratedText(content, self.name, self.name == "local", calls)


def configured_providers() -> dict[str, OpenAICompatibleProvider]:
    providers = {}
    if settings.local_llm_base_url:
        providers["local"] = OpenAICompatibleProvider(
            "local",
            settings.local_llm_base_url,
            settings.local_llm_api_key.get_secret_value() if settings.local_llm_api_key else None,
            settings.local_llm_model,
        )
    if settings.groq_api_key:
        providers["groq"] = OpenAICompatibleProvider(
            "groq",
            settings.groq_base_url,
            settings.groq_api_key.get_secret_value(),
            settings.groq_model,
        )
    if settings.sarvam_api_key:
        providers["sarvam"] = OpenAICompatibleProvider(
            "sarvam",
            settings.sarvam_base_url.rstrip("/") + "/v1",
            settings.sarvam_api_key.get_secret_value(),
            settings.sarvam_model,
        )
    if settings.gemini_api_key:
        providers["gemini"] = OpenAICompatibleProvider(
            "gemini",
            settings.gemini_base_url,
            settings.gemini_api_key.get_secret_value(),
            settings.gemini_model,
        )
    return providers
