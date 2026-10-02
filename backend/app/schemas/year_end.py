"""Year end, trial-balance version, and prior-year request models."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class YearEndCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    period_start: date
    period_end: date
    pack_id: str = "frs102-1a-ie"
    pack_version: str = "2024.09"


class YearEndResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    period_start: date | None
    period_end: date
    pack_id: str
    pack_version: str
    prior_year_validated: bool
    first_financial_period: bool


class TrialBalanceVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: uuid.UUID


class TrialBalanceVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    year_end_id: uuid.UUID
    version_number: int
    source_document_id: uuid.UUID
    status: str
    error_message: str | None
    draft_version_number: int | None = None


class PriorYearLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_line: str = Field(min_length=1, max_length=64)
    amount: str = Field(min_length=1, max_length=32)


class PriorYearConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[PriorYearLineIn]


class PriorYearLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_line: str
    amount: str


class PriorYearResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    prior_year_validated: bool
    first_financial_period: bool
    lines: list[PriorYearLineOut]


class ReconciliationGateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open: bool
    code: str | None
    severity: str | None
    passed: bool | None
    message: str | None


def amount_text(value: Decimal) -> str:
    return format(value, "f")
