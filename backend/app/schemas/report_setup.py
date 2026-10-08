"""Report-setup display settings. No statement amounts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from findraft.engine.pack import load_manifest

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


def pack_section_catalogue() -> dict[str, dict[str, str]]:
    """Section rules declared by the pinned pack. The engine does not call this."""
    manifest_obj: object = load_manifest()
    if not isinstance(manifest_obj, dict):
        raise ValueError("pack manifest is malformed")
    raw = manifest_obj.get("sections")
    if not isinstance(raw, list) or not raw:
        raise ValueError("pack sections are missing")
    catalogue: dict[str, dict[str, str]] = {}
    required = ("group", "default", "lock", "source_status", "label")
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("pack section is malformed")
        section_id = item.get("id")
        if not isinstance(section_id, str) or not section_id or section_id in catalogue:
            raise ValueError("pack section id is malformed")
        rule: dict[str, str] = {}
        for key in required:
            value = item.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(f"pack section {section_id} is missing {key}")
            rule[key] = value
        if rule["lock"] not in {"locked", "user"}:
            raise ValueError(f"pack section {section_id} lock is malformed")
        if rule["default"] not in {"on", "off", "engine"}:
            raise ValueError(f"pack section {section_id} default is malformed")
        catalogue[section_id] = rule
    return catalogue


class ReportSetupWrite(BaseModel):
    """Display fields a save may change. Basis stays on the year end.

    ``sections`` omitted means keep the stored map. A map replaces it.
    Absent keys inside the map mean the pack default.
    """

    model_config = ConfigDict(extra="forbid")

    rounding: RoundingMode
    statement_type: StatementType
    face_dates: FaceDates
    column_headers: ColumnHeaders
    sections: dict[str, bool] | None = None

    @field_validator("sections")
    @classmethod
    def sections_follow_the_pack(
        cls, value: dict[str, bool] | None
    ) -> dict[str, bool] | None:
        if value is None:
            return None
        catalogue = pack_section_catalogue()
        unknown = sorted(set(value) - set(catalogue))
        if unknown:
            raise ValueError(f"Unknown section {unknown[0]}")
        locked_off = sorted(
            section_id
            for section_id, enabled in value.items()
            if catalogue[section_id]["lock"] == "locked" and enabled is False
        )
        if locked_off:
            raise ValueError(f"Locked section cannot be turned off: {locked_off[0]}")
        return value


class ReportSetupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis_id: str
    basis_version: str
    basis_label: str
    rounding: RoundingMode
    statement_type: StatementType
    face_dates: FaceDates
    column_headers: ColumnHeaders
    sections: dict[str, bool] | None = None
    trial_balance_period_start: date | None
    trial_balance_period_end: date


class WorkspaceSectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    group: str
    group_label: str
    order: int
    lock: str | None = None
    default: str | None = None
    built: bool | None = None


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
