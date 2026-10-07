"""Report-setup display settings. No statement amounts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RoundingMode = Literal["unit", "thousands"]
StatementType = Literal["draft", "compilation"]


class FaceDates(BaseModel):
    """Dates printed on the face. They do not select a trial balance."""

    model_config = ConfigDict(extra="forbid")

    current_start: date | None = None
    current_end: date | None = None
    prior_start: date | None = None
    prior_end: date | None = None

    @model_validator(mode="after")
    def spans_run_forward(self) -> FaceDates:
        if (
            self.current_start is not None
            and self.current_end is not None
            and self.current_end < self.current_start
        ):
            raise ValueError("Current face end is before its start")
        if (
            self.prior_start is not None
            and self.prior_end is not None
            and self.prior_end < self.prior_start
        ):
            raise ValueError("Prior face end is before its start")
        return self


class ColumnHeaders(BaseModel):
    """Column words. as_at is a point in time. ended is a period."""

    model_config = ConfigDict(extra="forbid")

    as_at_current: str
    as_at_prior: str
    ended_current: str
    ended_prior: str

    @field_validator(
        "as_at_current",
        "as_at_prior",
        "ended_current",
        "ended_prior",
    )
    @classmethod
    def one_line_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 40 or "\n" in cleaned or "\r" in cleaned:
            raise ValueError("Column header must be 1 to 40 characters")
        return cleaned


class ReportSetupWrite(BaseModel):
    """The four display fields a save may change. Basis stays on the year end."""

    model_config = ConfigDict(extra="forbid")

    rounding: RoundingMode
    statement_type: StatementType
    face_dates: FaceDates
    column_headers: ColumnHeaders


class ReportSetupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis_id: str
    basis_version: str
    basis_label: str
    rounding: RoundingMode
    statement_type: StatementType
    face_dates: FaceDates
    column_headers: ColumnHeaders
    trial_balance_period_start: date | None
    trial_balance_period_end: date


class WorkspaceSectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str
    group_label: str
    order: int


class ReportingFrameworkOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    label: str
    available: bool
    sections: list[WorkspaceSectionOut]


class ReportingFrameworkList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frameworks: list[ReportingFrameworkOut] = Field(default_factory=list)
