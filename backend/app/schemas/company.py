"""Pydantic schemas for company API."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=500)
    company_number: str | None = None
    industry: str | None = None
    functional_currency: str | None = Field(default=None, min_length=3, max_length=3)


class CompanyUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=500)
    company_number: str | None = None
    industry: str | None = None
    functional_currency: str | None = Field(default=None, min_length=3, max_length=3)
    materiality_threshold_pct: Decimal | None = None
    materiality_threshold_abs: Decimal | None = None


class CompanyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    name: str
    company_number: str | None
    industry: str | None
    functional_currency: str
    materiality_threshold_pct: Decimal
    materiality_threshold_abs: Decimal
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CompanyListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: uuid.UUID
    items: list[CompanyResponse]
    total: int


class MappingListItem(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    source_code: str | None
    source_name: str
    canonical_line: str
    confidence: Decimal | None
    method: Literal["exact", "fuzzy", "code_range", "llm", "manual"]
    is_confirmed: bool
    is_ignored: bool
    created_at: datetime
    updated_at: datetime


class CompanyMappingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    mappings: list[MappingListItem]


class BulkDeleteMappingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    deleted_count: int


class ClientGroupMappingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: uuid.UUID
    mappings: list[MappingListItem]


class ClientGroupBulkDeleteMappingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: uuid.UUID
    deleted_count: int
