"""Pydantic schemas for client API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClientCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)


class ClientUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)


class ClientResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ClientListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ClientResponse]
    total: int
    limit: int
    offset: int
