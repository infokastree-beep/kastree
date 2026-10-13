"""Company letterhead and the year-end approval facts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.company import country_of_incorporation_code
from app.services.legal_forms import legal_form_code


class DirectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    appointed_on: date | None = None
    resigned_on: date | None = None


class AdviserRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class ShareClassWrite(BaseModel):
    """Issued amount is not accepted. Python multiplies issued by nominal."""

    model_config = ConfigDict(extra="forbid")

    class_name: str = Field(min_length=1, max_length=100)
    authorised_number: int | None = Field(default=None, ge=0)
    issued_number: int = Field(ge=0)
    nominal_value: str = Field(min_length=1, max_length=40)


class ShareClassOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_name: str
    authorised_number: int | None
    issued_number: int
    nominal_value: str
    issued_amount: str


class CompanyDetailsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_of_incorporation: str | None = None
    legal_form: str | None = None
    registered_office: str | None = None
    business_address: str | None = None
    company_number: str | None = None
    incorporated_on: date | None = None
    principal_activity: str | None = None
    secretary: str | None = None
    average_employees: int | None = Field(default=None, ge=0, le=1_000_000)
    directors: list[DirectorRecord] = Field(default_factory=list)
    advisers: list[AdviserRecord] = Field(default_factory=list)
    share_classes: list[ShareClassWrite] = Field(default_factory=list)

    @field_validator("country_of_incorporation", mode="before")
    @classmethod
    def _country(cls, value: object) -> str | None:
        return country_of_incorporation_code(value)

    @field_validator("legal_form", mode="before")
    @classmethod
    def _legal_form(cls, value: object) -> str | None:
        return legal_form_code(value)


class ApprovalWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_date: date | None = None
    signing_directors: list[str] = Field(default_factory=list)


class HoldingWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    undertaking: str = Field(min_length=1, max_length=200)
    shares: int = Field(ge=0)
    amount: str = Field(min_length=1, max_length=40)


class InterestEndWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interested: bool
    holdings: list[HoldingWrite] = Field(default_factory=list)


class ShareInterestWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    role: Literal["director", "secretary"]
    at_start: InterestEndWrite
    at_end: InterestEndWrite


class DirectorsReportWrite(BaseModel):
    """Typed directors' report facts. A blank amount stays not recorded."""

    model_config = ConfigDict(extra="forbid")

    accounting_records_location: str | None = None
    interim_dividend: str | None = None
    recommended_dividend: str | None = None
    share_interests: list[ShareInterestWrite] = Field(default_factory=list)
    own_shares_particulars: str | None = None
    subsequent_events_particulars: str | None = None
    research_development_relevant: bool | None = None
    research_development_detail: str | None = None
    political_donations_relevant: bool | None = None
    political_donations_detail: str | None = None
    accounting_period_change_filed: bool | None = None


class HoldingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    undertaking: str
    shares: int
    amount: str


class InterestEndOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interested: bool
    holdings: list[HoldingOut]


class ShareInterestOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: Literal["director", "secretary"]
    at_start: InterestEndOut
    at_end: InterestEndOut


class CurrencyConfirmationResponse(BaseModel):
    """Acknowledgement only. No amount is stored or converted."""

    model_config = ConfigDict(extra="forbid")

    year_end_id: uuid.UUID
    currency: str
    confirmed_at: datetime
    confirmed_by_user_id: uuid.UUID


class CompanyDetailsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_of_incorporation: str | None
    # Optional so a final snapshot saved before this field still validates.
    legal_form: str | None = None
    registered_office: str | None
    business_address: str | None
    company_number: str | None
    incorporated_on: date | None
    principal_activity: str | None
    secretary: str | None
    average_employees: int | None
    directors: list[DirectorRecord]
    advisers: list[AdviserRecord]
    share_classes: list[ShareClassOut]
    approval_date: date | None
    signing_directors: list[str]
    # Optional so a final snapshot saved before these facts still validates.
    accounting_records_location: str | None = None
    interim_dividend: str | None = None
    recommended_dividend: str | None = None
    share_interests: list[ShareInterestOut] = Field(default_factory=list)
    own_shares_particulars: str | None = None
    subsequent_events_particulars: str | None = None
    research_development_relevant: bool | None = None
    research_development_detail: str | None = None
    political_donations_relevant: bool | None = None
    political_donations_detail: str | None = None
    accounting_period_change_filed: bool | None = None
