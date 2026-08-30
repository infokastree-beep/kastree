"""Pydantic schemas for organisation API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrganisationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    name: str
    subscription_tier: str
    subscription_status: str
    functional_currency: str
    created_at: datetime


class OrganisationUpdateRequest(BaseModel):
    """Updatable org settings. Billing fields may appear but are never applied.

    subscription_tier / subscription_status are listed explicitly so a client
    can send them without a 422, while the router strips them before any write
    (Stripe webhook is the only writer — §4.5 / subscription_events).
    """

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    functional_currency: str | None = Field(default=None, min_length=3, max_length=3)
    # Explicitly acknowledged + ignored by the router (not updatable here).
    subscription_tier: str | None = None
    subscription_status: str | None = None


class MemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    email: str
    role: Literal["owner", "admin", "member", "viewer"]
    last_login_at: datetime | None
    created_at: datetime


class MemberListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    members: list[MemberResponse]


class InviteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: Literal["admin", "member", "viewer"] = "member"


class InviteStubResponse(BaseModel):
    """Returned when invites cannot be persisted — no invites table in §9.1 DDL."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["stub_pending_schema"]
    email: str
    role: str
    invited_by_user_id: uuid.UUID
    detail: str
