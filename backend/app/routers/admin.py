"""Owner-only platform admin overview (cross-tenant reads)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_platform_admin
from app.dependencies import AuthContext, get_db_session, require_roles
from app.models.organisation import Organisation
from app.models.user import User
from app.models.waitlist_signup import WaitlistSignup
from app.schemas.admin import AdminOverviewResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(
    auth: Annotated[AuthContext, Depends(require_roles("owner"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminOverviewResponse:
    """Platform-wide signups for Owners — requires platform_admin RLS read path."""
    _ = auth
    # get_auth_context (via require_roles) always SET LOCAL app.current_org_id first;
    # do not call aset_platform_admin before that or organisations_self_isolation
    # can error on its UUID cast when current_org_id is unset.
    await aset_platform_admin(session)

    waitlist_rows = (
        await session.scalars(
            select(WaitlistSignup).order_by(WaitlistSignup.created_at.desc())
        )
    ).all()
    org_rows = (
        await session.scalars(
            select(Organisation).order_by(Organisation.created_at.desc())
        )
    ).all()
    user_rows = (
        await session.execute(
            select(User, Organisation.name)
            .join(Organisation, User.org_id == Organisation.id)
            .order_by(User.created_at.desc())
        )
    ).all()

    return AdminOverviewResponse.from_rows(
        waitlist_rows=waitlist_rows,
        organisation_rows=org_rows,
        user_rows=user_rows,
    )
