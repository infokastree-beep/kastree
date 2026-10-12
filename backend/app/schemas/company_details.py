"""Company letterhead and the year-end approval facts."""

from __future__ import annotations

import uuid
from datetime import date, datetime

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
