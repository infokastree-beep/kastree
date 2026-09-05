"""Schemas for materiality auto-suggestion (tracked-gaps ISA 320 defaults)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CompanyType = Literal["trading", "holding"]
BenchmarkBasis = Literal["profit_before_tax", "total_equity"]


class MaterialitySuggestionResponse(BaseModel):
    """GET /trial-balances/{id}/materiality-suggestion.

    ``available`` is True only when a mid-range ISA 320-style suggestion can be
    computed from statement figures AND it meaningfully differs from the
    company's current thresholds AND the soft banner has not been dismissed.
    """

    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    company_id: uuid.UUID
    available: bool
    message: str | None = None
    company_type: CompanyType
    benchmark_basis: BenchmarkBasis | None = None
    benchmark_amount: str | None = None
    range_pct_low: str | None = None
    range_pct_high: str | None = None
    suggested_pct: str | None = None
    suggested_abs: str | None = None
    current_pct: str
    current_abs: str
    dismissed: bool = False
    disclaimer: str = Field(
        default=(
            "Indicative SaaS default from ISA 320-style benchmarks — "
            "not an audit determination."
        )
    )


class MaterialitySuggestionDismissResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    materiality_suggestion_dismissed_at: str
