"""Admin overview response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from app.models.organisation import Organisation
from app.models.user import User
from app.models.waitlist_signup import WaitlistSignup


class WaitlistSignupAdminItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: str
    firm: str
    role: str
    created_at: datetime


class OrganisationAdminItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    subscription_tier: str
    subscription_status: str
    created_at: datetime
    product2_access: Literal["On", "Off"]
    product2_acknowledged_by: str | None
    product2_acknowledged_at: datetime | None


class Product2AccessAdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged: bool


class Product2AccessAdminResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    org_id: uuid.UUID
    acknowledged: bool
    recorded: bool


class UserAdminItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    role: str
    organisation_name: str
    created_at: datetime


class AdminOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    waitlist_count: int
    waitlist_signups: list[WaitlistSignupAdminItem]
    organisations_count: int
    organisations: list[OrganisationAdminItem]
    users_count: int
    users: list[UserAdminItem]

    @classmethod
    def from_rows(
        cls,
        *,
        waitlist_rows: Sequence[WaitlistSignup],
        organisation_rows: Sequence[Organisation],
        user_rows: Sequence[tuple[User, str]],
        acknowledger_emails: dict[uuid.UUID, str],
    ) -> AdminOverviewResponse:
        waitlist_items = [
            WaitlistSignupAdminItem(
                name=row.name,
                email=row.email,
                firm=row.firm,
                role=row.role,
                created_at=row.created_at,
            )
            for row in waitlist_rows
        ]
        organisation_items = [
            OrganisationAdminItem(
                id=row.id,
                name=row.name,
                subscription_tier=row.subscription_tier,
                subscription_status=row.subscription_status,
                created_at=row.created_at,
                product2_access="On"
                if row.product2_acknowledged_at is not None
                else "Off",
                product2_acknowledged_by=(
                    None
                    if row.product2_acknowledged_by_user_id is None
                    else acknowledger_emails.get(row.product2_acknowledged_by_user_id)
                ),
                product2_acknowledged_at=row.product2_acknowledged_at,
            )
            for row in organisation_rows
        ]
        user_items = [
            UserAdminItem(
                email=user.email,
                role=user.role,
                organisation_name=org_name,
                created_at=user.created_at,
            )
            for user, org_name in user_rows
        ]
        return cls(
            waitlist_count=len(waitlist_items),
            waitlist_signups=waitlist_items,
            organisations_count=len(organisation_items),
            organisations=organisation_items,
            users_count=len(user_items),
            users=user_items,
        )
