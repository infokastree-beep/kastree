"""Pydantic schemas for notifications API (§10.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationType = Literal[
    "processing_complete",
    "export_ready",
    "validation_failed",
    "llm_unavailable",
    "billing_alert",
]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    org_id: uuid.UUID
    type: NotificationType
    title: str
    message: str
    is_read: bool
    action_url: str | None
    created_at: datetime


class NotificationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int


class MarkReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    is_read: bool


class MarkAllReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    updated_count: int = Field(ge=0)
