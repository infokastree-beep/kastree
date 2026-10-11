"""Current-user response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Product2AccessResponse(BaseModel):
    """Whether this practice may open statutory drafts, and who turned that on."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    acknowledged: bool
    source: Literal["practice", "admin"] | None
    wording_signed_off: Literal[False]


class UserMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    org_id: str
    email: str
    role: Literal["owner", "admin", "member", "viewer"]
    is_platform_admin: bool
    product2_access: Product2AccessResponse
