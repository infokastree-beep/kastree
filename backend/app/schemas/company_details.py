"""Company letterhead and the year-end approval facts."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class DirectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    appointed_on: date | None = None
    resigned_on: date | None = None


class CompanyDetailsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registered_office: str | None = None
    business_address: str | None = None
    company_number: str | None = None
    incorporated_on: date | None = None
    principal_activity: str | None = None
    secretary: str | None = None
    average_employees: int | None = Field(default=None, ge=0, le=1_000_000)
    directors: list[DirectorRecord] = Field(default_factory=list)


class ApprovalWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_date: date | None = None
    signing_directors: list[str] = Field(default_factory=list)


class CompanyDetailsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registered_office: str | None
    business_address: str | None
    company_number: str | None
    incorporated_on: date | None
    principal_activity: str | None
    secretary: str | None
    average_employees: int | None
    directors: list[DirectorRecord]
    approval_date: date | None
    signing_directors: list[str]
