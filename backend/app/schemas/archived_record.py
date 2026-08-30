"""Pydantic schemas for archived_records API (§10.2 / §12.2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ArchivedRecordSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    client_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID
    archive_reason: str
    archive_hash: str
    retention_until: date
    created_at: datetime


class ArchivedRecordListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ArchivedRecordSummary]


class ArchivedRecordDetailResponse(BaseModel):
    """GET /archived-records/{id} — includes server-side hash verification."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    org_id: uuid.UUID
    client_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID
    archive_reason: str
    archived_by_user_id: uuid.UUID | None
    archived_data: dict
    archive_hash: str
    retention_until: date
    created_at: datetime
    hash_verified: bool = Field(
        description="True when SHA-256(archived_data) matches archive_hash"
    )
