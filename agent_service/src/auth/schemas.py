from typing import Literal

from pydantic import BaseModel, Field


class Principal(BaseModel):
    user_id: str
    role: str = "citizen"


class DevTokenResponse(BaseModel):
    token: str


class DevTokenRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    role: Literal["citizen", "admin", "crew"] = "citizen"
