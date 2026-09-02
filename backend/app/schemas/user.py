"""Current-user response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UserMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    org_id: str
    email: str
    role: Literal["owner", "admin", "member", "viewer"]
