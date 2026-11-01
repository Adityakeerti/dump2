from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class GeneratedText:
    text: str
    provider: str
    fallback: bool = False
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class TextProvider(Protocol):
    name: str

    async def generate(
        self,
        *,
        system: str,
        user: str,
        context: list[str],
        language: str | None,
        tools: list[dict] | None = None,
        history: list[dict] | None = None,
    ) -> GeneratedText: ...


class SpeechProvider(Protocol):
    name: str

    async def transcribe(
        self, data: bytes, filename: str, language: str | None
    ) -> tuple[str, str | None]: ...
