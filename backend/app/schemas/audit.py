"""Audit log and erasure responses."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RetentionPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statutory_floor_years: int
    retention_years: int
    buffer_is_statutory: bool
    erasure_replaces: list[str]
    erasure_retains: list[str]
    statement: str


class AuditChainResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    count: int
    chain_valid: bool


class ErasureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: Literal["client", "user"]
    entity_id: uuid.UUID
    erased: bool
    retained: list[str] = Field(default_factory=list)
    statement: str
