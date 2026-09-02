"""Admin overview response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

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

    name: str
    subscription_tier: str
    subscription_status: str
    created_at: datetime


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
                name=row.name,
                subscription_tier=row.subscription_tier,
                subscription_status=row.subscription_status,
                created_at=row.created_at,
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
