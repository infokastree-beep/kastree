"""Year end, trial-balance version, and prior-year request models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def size_amount_text(value: Decimal | None) -> str | None:
    """Exact cent text. A Decimal from the year-end row is not sent as a float."""
    if value is None:
        return None
    return format(value, "f")


def decimal_text(value: object) -> str | None:
    """Exact cent text. A Decimal from the year-end row is not sent as a float."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return size_amount_text(value)
    if isinstance(value, str):
        return value
    raise ValueError("A size amount must be decimal text")


SizeAmountOut = Annotated[str | None, BeforeValidator(decimal_text)]


class YearEndCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    period_start: date
    period_end: date
    pack_id: str = "frs102-1a-ie"
    pack_version: str = "2024.09"


class StatutoryYearEndContinueRequest(BaseModel):
    """Pin a year end from a Product 1 trial balance already on the statements page."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str = "frs102-1a-ie"
    pack_version: str = "2024.09"


class StatutoryYearEndLink(BaseModel):
    """The year end already pinned for this trial balance's company and period."""

    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID


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
    adopted_trial_balance_id: uuid.UUID | None = None
    size_current_turnover: SizeAmountOut = None
    size_current_balance_sheet: SizeAmountOut = None
    size_current_employees: int | None = None
    size_preceding_turnover: SizeAmountOut = None
    size_preceding_balance_sheet: SizeAmountOut = None
    size_preceding_employees: int | None = None
    size_message: str | None = None
    audit_exemption_claimed: bool | None = None
    audit_exemption_claimed_by_user_id: uuid.UUID | None = None
    audit_exemption_claimed_at: datetime | None = None
    audit_exemption_not_excluded: bool | None = None
    audit_exemption_no_member_notice: bool | None = None
    audit_exemption_returns_not_late: bool | None = None
    audit_exemption_conditions_by_user_id: uuid.UUID | None = None
    audit_exemption_conditions_at: datetime | None = None


class AuditExemptionRequest(BaseModel):
    """True is claimed, false is not claimed, null clears the position."""

    model_config = ConfigDict(extra="forbid")

    claimed: bool | None


class AuditExemptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    claimed: bool | None
    claimed_by_user_id: uuid.UUID | None
    claimed_at: datetime | None


class AuditExemptionConditionsRequest(BaseModel):
    """The three directors' confirmations, recorded together or cleared together."""

    model_config = ConfigDict(extra="forbid")

    not_excluded: bool | None
    no_member_notice: bool | None
    returns_not_late: bool | None

    @model_validator(mode="after")
    def recorded_together(self) -> AuditExemptionConditionsRequest:
        values = (self.not_excluded, self.no_member_notice, self.returns_not_late)
        if any(item is None for item in values) and any(
            item is not None for item in values
        ):
            raise ValueError(
                "Record all three directors' confirmations together, or clear them together."
            )
        return self


class AuditExemptionConditionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    not_excluded: bool | None
    no_member_notice: bool | None
    returns_not_late: bool | None
    conditions_by_user_id: uuid.UUID | None
    conditions_at: datetime | None


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
    draft_id: uuid.UUID | None = None


class TrialBalanceLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int
    nominal_code: str
    account_name: str
    debit: str
    credit: str
    suggested_canonical_line: str | None = None
    confidence: str | None = None
    method: str | None = None


class TrialBalanceLinesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[TrialBalanceLineOut]


class CanonicalLinesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[str]


class PriorYearLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_line: str = Field(min_length=1, max_length=64)
    amount: str = Field(min_length=1, max_length=32)


class PriorYearConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[PriorYearLineIn]
    matches_filed_accounts: bool | None = None


class PriorYearLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    canonical_line: str
    amount: str


class PriorYearResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    prior_year_validated: bool
    first_financial_period: bool
    comparative_source: str | None = None
    lines: list[PriorYearLineOut]


class MappingDifferenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_code: str
    account_name: str
    previous_line: str
    current_line: str


class PriorYearCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    passed: bool | None
    message: str


class PriorYearSourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    preferred: bool
    available: bool
    refusal: str | None
    guidance: str | None
    trial_balance_id: uuid.UUID | None
    year_end_id: uuid.UUID | None
    draft_id: uuid.UUID | None
    period_start: date | None
    period_end: date | None
    lines: list[PriorYearLineOut]
    mapping_differences: list[MappingDifferenceOut]
    checks: list[PriorYearCheckOut]


class PriorYearPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    prior_year_validated: bool
    first_financial_period: bool
    comparative_source: str | None
    stored_lines: list[PriorYearLineOut]
    stale_notice: str | None
    face_date_notice: str | None
    sources: list[PriorYearSourceOut]


class PriorYearTrialBalanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool
    mapping_differences_confirmed: bool = False


class PriorYearFinalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: bool


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


class EvidenceAccountOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_line_id: uuid.UUID | None
    nominal_code: str
    account_name: str
    mapped_line: str
    presented_line: str
    balance: str
    contribution: str
    source_document_id: uuid.UUID | None


class EvidenceLineOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    label: str
    amount: str
    accounts: list[EvidenceAccountOut]
    components: list[str]


class EvidenceDocumentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    filename: str
    detected_type: str
    role: Literal["trial_balance"]
    file_hash: str | None = None


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    renderable: bool
    blocked: bool
    build_error: str | None
    checks: list[ReconciliationCheckOut]
    documents: list[EvidenceDocumentOut]
    lines: list[EvidenceLineOut]


class StatutoryPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    paragraphs: list[str]


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
    company_name: str = ""
    pages: list[StatutoryPageOut] = Field(default_factory=list)
    engine_turnover: str | None = None
    engine_balance_sheet_total: str | None = None
    omitted_blocks: list[str] = Field(default_factory=list)
    added_blocks: list[str] = Field(default_factory=list)


class SizeEligibilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    eligible: bool
    current_conditions_met: int
    preceding_conditions_met: int | None
    message: str
    size_current_turnover: SizeAmountOut = None
    size_current_balance_sheet: SizeAmountOut = None
    size_current_employees: int | None = None
    size_preceding_turnover: SizeAmountOut = None
    size_preceding_balance_sheet: SizeAmountOut = None
    size_preceding_employees: int | None = None


class DashboardFixOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    note: str | None = None
    anchor: str | None = None


class DashboardCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: str
    passed: bool
    message: str
    area: str = "Other"
    fix: DashboardFixOut | None = None


class DisclosureQuestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_name: str
    question: str
    group: str
    note: str | None = None
    answer: Literal["yes", "no", "unanswered"]


class DraftStatusView(BaseModel):
    """Lifecycle is Draft or Final. Readiness is present only while Draft."""

    model_config = ConfigDict(extra="forbid")

    lifecycle: Literal["Draft", "Final"]
    readiness: str | None = None


class DashboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    status: str
    row_version: int
    traffic: Literal["red", "amber", "green"]
    can_finalise: bool
    status_view: DraftStatusView
    unanswered_disclosures: list[str]
    unanswered_count: int = 0
    blocking_count: int = 0
    carried_disclosures: list[str] = Field(default_factory=list)
    disclosure_questions: list[DisclosureQuestionOut] = Field(default_factory=list)
    checks: list[DashboardCheckOut]


class AdjustmentLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_code: str = Field(min_length=1, max_length=64)
    account_name: str = Field(min_length=1, max_length=255)
    canonical_line: str = Field(min_length=1, max_length=64)
    debit: str = Field(min_length=1, max_length=32)
    credit: str = Field(min_length=1, max_length=32)


class AdjustmentPostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)
    narration: str = Field(min_length=1, max_length=500)
    lines: list[AdjustmentLineIn] = Field(min_length=2)


class AdjustmentPostResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    journal_id: uuid.UUID
    draft_id: uuid.UUID
    row_version: int
    line_count: int


class DisclosureAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)
    flag_name: str = Field(min_length=1, max_length=64)
    answer: Literal["yes", "no", "unanswered"]


class DisclosureAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    row_version: int
    flag_name: str
    answer: Literal["yes", "no", "unanswered"]


class MarkRemainingNoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)
    confirm: bool


class MarkRemainingNoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    row_version: int
    count: int
    flag_ids: list[str]


class NoteLibraryRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    title: str
    reason: Literal[
        "always",
        "trial_balance",
        "disclosure_yes",
        "unanswered",
        "disclosure_no",
        "omitted",
        "added",
    ]
    sentence: str
    can_omit: bool
    can_restore: bool
    can_add: bool
    can_remove: bool
    kind: Literal["Note", "Policy"]
    note_class: str
    note_class_label: str


class NoteLibraryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    row_version: int
    rows: list[NoteLibraryRowOut]


class NoteLibraryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)
    block_id: str = Field(min_length=1, max_length=64)
    action: Literal["omit", "restore", "add", "remove"]


class NoteLibraryMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    row_version: int
    block_id: str
    action: Literal["omit", "restore", "add", "remove"]


class DraftMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)


class FinaliseRequest(BaseModel):
    """Finalise one draft. The review flag is required when answers were copied."""

    model_config = ConfigDict(extra="forbid")

    row_version: int = Field(ge=1)
    reviewed_carried_disclosures: bool = False


class DraftStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    status: str
    row_version: int


class WorkingDraftResponse(BaseModel):
    """Latest draft version for a year end. The workspace page reloads this."""

    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    version_number: int
    status: str
    row_version: int
    tb_version_id: uuid.UUID | None
    mapping_notice: str | None = None
    frozen: bool = False


class NewDraftVersionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    version_number: int
    row_version: int
    status: str


class FinaliseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: uuid.UUID
    status: str
    row_version: int
    inputs_sha256: str
    engine_sha: str
    pack_id: str
    pack_version: str
    traffic: Literal["red", "amber", "green"]


class RenderJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: uuid.UUID
    status: Literal["pending", "running", "ready", "failed"]
    error_message: str | None = None


class AdoptableTrialBalanceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    period_end: date
    currency: str | None
    account_count: int


class AdoptableTrialBalanceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AdoptableTrialBalanceOut]


class TrialBalancePageResponse(BaseModel):
    """Read-only Inputs page. ``file_name`` stays null until a name is stored."""

    model_config = ConfigDict(extra="forbid")

    trial_balance_id: uuid.UUID | None
    period_start: date | None
    period_end: date | None
    uploaded_at: datetime | None
    account_count: int | None
    currency: str | None
    file_name: str | None


class AdoptTrialBalanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trial_balance_id: uuid.UUID


class CarriedMappingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_code: str
    account_name: str
    product1_line: str
    canonical_line: str
    suggested_line: str | None = None
    suggestion_confidence: str | None = None


class StatutorySublineRowOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_code: str
    account_name: str
    product1_line: str
    suggested_line: str | None
    suggestion_confidence: str | None
    statutory_line: str | None
    choices: list[str]


class StatutorySublineReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    blocked: bool
    rows: list[StatutorySublineRowOut]


class StatutorySublineChoiceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nominal_code: str
    account_name: str
    statutory_line: str


class StatutorySublineConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[StatutorySublineChoiceIn]


class AdoptedTrialBalanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    trial_balance_id: uuid.UUID
    lines: list[CarriedMappingOut]
