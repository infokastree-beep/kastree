"""Owner-only platform admin overview (cross-tenant reads)."""

from __future__ import annotations

from typing import Annotated

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_platform_admin, aset_rls_org_id
from app.dependencies import AuthContext, get_db_session, require_platform_admin
from app.models.organisation import Organisation
from app.models.user import User
from app.models.waitlist_signup import WaitlistSignup
from app.schemas.admin import (
    AdminOverviewResponse,
    Product2AccessAdminRequest,
    Product2AccessAdminResponse,
)
from app.services.beta import set_product2_access

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(
    auth: Annotated[AuthContext, Depends(require_platform_admin())],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminOverviewResponse:
    """Platform-wide signups for platform admins — owner role + PLATFORM_ADMIN_EMAILS."""
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

    acknowledger_ids = {
        row.product2_acknowledged_by_user_id
        for row in org_rows
        if row.product2_acknowledged_by_user_id is not None
    }
    acknowledger_emails: dict[uuid.UUID, str] = {}
    if acknowledger_ids:
        acknowledgers = (
            await session.scalars(select(User).where(User.id.in_(acknowledger_ids)))
        ).all()
        acknowledger_emails = {user.id: user.email for user in acknowledgers}
    return AdminOverviewResponse.from_rows(
        waitlist_rows=waitlist_rows,
        organisation_rows=org_rows,
        user_rows=user_rows,
        acknowledger_emails=acknowledger_emails,
    )


@router.post(
    "/organisations/{org_id}/product2-access",
    response_model=Product2AccessAdminResponse,
)
async def post_product2_access(
    org_id: uuid.UUID,
    body: Product2AccessAdminRequest,
    auth: Annotated[AuthContext, Depends(require_platform_admin())],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Product2AccessAdminResponse:
    """Grant or revoke Product 2 for one practice.

    The practice cannot clear its own acknowledgement. This handler sets
    ``app.current_org_id`` to the target practice for this transaction only,
    then writes the two acknowledgement columns and one audit row there.
    """
    await aset_rls_org_id(session, org_id)
    recorded = await set_product2_access(
        session,
        org_id=org_id,
        actor_user_id=auth.user_id,
        acknowledged=body.acknowledged,
    )
    if recorded is None:
        raise HTTPException(status_code=404, detail="Organisation not found")
    return Product2AccessAdminResponse(
        org_id=org_id,
        acknowledged=body.acknowledged,
        recorded=recorded,
    )
