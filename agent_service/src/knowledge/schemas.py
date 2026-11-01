from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tenant_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl | None = None
    jurisdiction: str = Field(min_length=1, max_length=100)
    language: Literal["en", "hi"]
    published_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("source_url")
    @classmethod
    def source_url_without_credentials(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value and (len(str(value)) > 2000 or value.username or value.password):
            raise ValueError(
                "Source URL must be at most 2000 characters and contain no credentials"
            )
        return value

    @field_validator("published_at", "expires_at")
    @classmethod
    def aware_dates(cls, value: datetime | None) -> datetime | None:
        if value and value.tzinfo is None:
            raise ValueError("Use an ISO-8601 timestamp with timezone")
        return value

    @model_validator(mode="after")
    def valid_dates(self):
        if self.published_at and self.expires_at and self.expires_at <= self.published_at:
            raise ValueError("expires_at must be after published_at")
        return self


class DocumentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    doc_id: UUID
    tenant_id: str
    title: str
    publisher: str
    source_url: str | None
    jurisdiction: str
    language: str
    verification_status: str
    ingestion_status: str
    ingestion_error: str | None
    fetched_at: datetime
    expires_at: datetime | None


class VerificationRequest(BaseModel):
    status: Literal["verified", "rejected"]
