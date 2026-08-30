"""Pydantic schemas for variance_analyses.items JSONB and variance API (§10.3)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.commentary import CommentaryRecord

VarianceDirection = Literal["increase", "decrease", "new", "removed"]


class VarianceItemRecord(BaseModel):
    """One variance row stored in variance_analyses.items (minus commentary)."""

    model_config = ConfigDict(extra="forbid")

    line_item_code: str
    line_item_name: str
    current_amount: str
    prior_amount: str
    variance_amount: str
    variance_pct: str | None = None
    direction: VarianceDirection
    is_material: bool


class VarianceAnalysisResult(BaseModel):
    """Canonical shape for variance_analyses.items JSONB payload."""

    model_config = ConfigDict(extra="forbid")

    items: list[VarianceItemRecord]

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB storage via SQLAlchemy."""
        return self.model_dump(mode="json", exclude_none=True)


class VarianceGenerateRequest(BaseModel):
    """Optional explicit prior TB; omit to auto-detect (§6.2)."""

    model_config = ConfigDict(extra="forbid")

    prior_tb_id: uuid.UUID | None = None


class VarianceItemResponse(BaseModel):
    """One variance row in the §10.3 API response (optional commentary)."""

    model_config = ConfigDict(extra="forbid")

    line_item_code: str
    line_item_name: str
    current_amount: str
    prior_amount: str
    variance_amount: str
    variance_pct: str | None = None
    direction: VarianceDirection
    is_material: bool
    commentary: CommentaryRecord | None = None


class VarianceResponse(BaseModel):
    """GET/POST /trial-balances/{id}/variance response (§10.3 + §7 missing-prior)."""

    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    prior_tb_id: uuid.UUID | None = None
    variance_available: bool
    message: str | None = None
    materiality_threshold_pct: float | None = None
    materiality_threshold_abs: str | None = None
    items: list[VarianceItemResponse] = Field(default_factory=list)


MISSING_PRIOR_PERIOD_MESSAGE = (
    "Upload prior period TB to enable variance analysis."
)

PRIOR_STATEMENTS_MISSING_MESSAGE = (
    "Prior period statements have not been generated yet. "
    "Generate statements for the prior trial balance to enable variance analysis."
)
