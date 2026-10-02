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


class FixedAssetVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_document_id: uuid.UUID


class FixedAssetLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_class: str
    opening_cost: str
    additions: str
    disposals: str
    disposals_dep: str
    opening_dep: str
    charge: str


class FixedAssetTotalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening_cost: str
    additions: str
    disposals: str
    disposals_dep: str
    closing_cost: str
    opening_dep: str
    charge: str
    closing_dep: str
    nbv_close: str
    nbv_open: str


class FixedAssetVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    year_end_id: uuid.UUID
    version_number: int
    source_document_id: uuid.UUID
    status: str
    error_message: str | None
    lines: list[FixedAssetLineOut]
    total: FixedAssetTotalOut | None
    invariant_holds: bool | None


class SizeYearIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turnover: str = Field(min_length=1, max_length=32)
    balance_sheet_total: str = Field(min_length=1, max_length=32)
    employees: int = Field(ge=0)


class SizeEligibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: SizeYearIn
    preceding: SizeYearIn | None = None


class MappingLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_code: str = Field(min_length=1, max_length=64)
    canonical_line: str = Field(min_length=1, max_length=64)


class MappingConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[MappingLineIn]


class MappingLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_code: str
    canonical_line: str


class MappingConfirmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_version_id: uuid.UUID
    lines: list[MappingLineOut]


class ReconciliationCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str
    passed: bool
    message: str


class ReconciliationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked: bool
    build_error: str | None
    checks: list[ReconciliationCheckOut]
    net_assets: str | None
    profit: str | None


class StatementRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    current: str
    prior: str | None


class NoteLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line: str
    current: str
    prior: str


class FixedAssetGridRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_class: str
    opening_cost: str
    additions: str
    disposals: str
    disposals_dep: str
    closing_cost: str
    opening_dep: str
    charge: str
    closing_dep: str
    nbv_close: str
    nbv_open: str


class RoundingFlagOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_line_id: str
    flagged: bool
    gap: str
    deeplink: str | None


class StatementNoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    title: str | None
    body: str
    lines: list[NoteLineOut]
    fa_rows: list[FixedAssetGridRowOut]


class StatementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watermark: str
    renderable: bool
    blocked: bool
    build_error: str | None
    checks: list[ReconciliationCheckOut]
    net_assets: str | None
    profit: str | None
    compliance_statement: str | None
    sofp: list[StatementRowOut]
    income: list[StatementRowOut]
    notes: list[StatementNoteOut]
    rounding_flags: list[RoundingFlagOut]


class SizeEligibilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    eligible: bool
    current_conditions_met: int
    preceding_conditions_met: int | None
    message: str
