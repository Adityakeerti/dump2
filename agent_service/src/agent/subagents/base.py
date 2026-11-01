from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.schemas import Principal


class SubAgentResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    response_text: str
    sources: list[Any] = Field(default_factory=list)
    action: dict[str, Any] | None = None
    cta: str | None = None
    execution_steps: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseSubAgent(ABC):
    name: str = "base"
    description: str = "Base subagent"

    @abstractmethod
    async def execute(
        self,
        session: AsyncSession | None,
        principal: Principal,
        message: str,
        context: Any = None,
        language: str = "en",
        **kwargs: Any,
    ) -> SubAgentResult:
        """Execute deterministic SOP steps and return a SubAgentResult."""
        pass
