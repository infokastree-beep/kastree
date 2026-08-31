"""Waitlist signup request/response schemas."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class WaitlistSignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    firm: str = Field(min_length=1, max_length=200)
    role: str = Field(min_length=1, max_length=120)
    approx_client_count: str | None = Field(default=None, max_length=80)
    pain_point: str | None = Field(default=None, max_length=2000)


class WaitlistSignupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str = "registered"
