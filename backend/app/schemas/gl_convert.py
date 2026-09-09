"""Schemas for Phase 3 GL → TB conversion (review only — no TB created)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.pdf_extract import ExtractedTbRowOut, MoneyStr

OpeningBalanceModeOut = Literal["A", "B", "C"]


class GlConvertResponse(BaseModel):
    """Candidate TB rows for review — not yet a TrialBalance."""

    model_config = ConfigDict(extra="forbid")

    rows: list[ExtractedTbRowOut]
    mode: OpeningBalanceModeOut
    period_start: date
    period_end: date
    included_count: int
    excluded_count: int
    opening_count: int
    total_debits: MoneyStr
    total_credits: MoneyStr
    pipeline_eligible: bool = True
    warnings: list[str] = Field(default_factory=list)
    message: str = (
        "Review and correct the converted trial balance rows, then confirm "
        "to continue with the normal upload pipeline."
    )


class GlImbalanceDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["GL_TB_UNBALANCED"] = "GL_TB_UNBALANCED"
    detail: str
    total_debits: MoneyStr
    total_credits: MoneyStr
    difference: MoneyStr
    mode: OpeningBalanceModeOut
    included_count: int
    excluded_count: int
    top_accounts: list[dict[str, str]]
