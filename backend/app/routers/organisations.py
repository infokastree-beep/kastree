"""Organisations API — current-org settings and member management (§10.2).

INVITES SCHEMA GAP (explicit):
  POST /organisations/me/invites is specified in §10.2, but Section 9.1's DDL has
  no ``invites`` (or equivalent) table. This router does NOT invent one. After the
  owner/admin role check, the handler returns a stub response
  (status=\"stub_pending_schema\") and persists nothing. Minimal fix before real
  invites work: add an invites migration (email, org_id, role, invited_by,
  status, token, expires_at) then wire Resend (post-MVP notifications).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session, require_roles
from app.models.organisation import Organisation
from app.models.user import User
from app.schemas.organisation import (
    InviteCreateRequest,
    InviteStubResponse,
    MemberListResponse,
    MemberResponse,
    OrganisationResponse,
    OrganisationUpdateRequest,
)

router = APIRouter(prefix="/organisations", tags=["organisations"])

# Stripe-webhook-driven columns — never writable via PUT /organisations/me.
_BILLING_FIELDS_NOT_UPDATABLE_HERE = frozenset(
    {
        "subscription_tier",
        "subscription_status",
        "stripe_customer_id",
        "stripe_subscription_id",
    }
)
_ORG_UPDATABLE_FIELDS = frozenset({"name", "functional_currency"})

INVITES_SCHEMA_GAP_DETAIL = (
    "No invites table exists in Product Spec §9.1 DDL. Invite was not persisted. "
    "Add an invites migration before enabling real pending-invite storage; "
    "email delivery via Resend is post-MVP."
)


async def _load_caller_org(
    session: AsyncSession,
    auth: AuthContext,
) -> Organisation:
    """Org from JWT-resolved auth.org_id; must exist and match the user row."""
    await aset_rls_org_id(session, auth.org_id)
    org = await session.get(Organisation, auth.org_id)
    if org is None:
        raise HTTPException(status_code=401, detail="Unknown organisation")
    user = await session.get(User, auth.user_id)
    if user is None or user.org_id != org.id:
        raise HTTPException(status_code=401, detail="Unknown user")
    return org


@router.get("/me", response_model=OrganisationResponse)
async def get_my_organisation(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Organisation:
    return await _load_caller_org(session, auth)


@router.put("/me", response_model=OrganisationResponse)
async def update_my_organisation(
    body: OrganisationUpdateRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Organisation:
    org = await _load_caller_org(session, auth)
    raw = body.model_dump(exclude_unset=True)
    # Explicit exclusion — billing fields are never applied even if present.
    for forbidden in _BILLING_FIELDS_NOT_UPDATABLE_HERE:
        raw.pop(forbidden, None)
    updates = {key: value for key, value in raw.items() if key in _ORG_UPDATABLE_FIELDS}
    if "name" in updates and updates["name"] is not None:
        updates["name"] = str(updates["name"]).strip()
    if "functional_currency" in updates and updates["functional_currency"] is not None:
        updates["functional_currency"] = str(updates["functional_currency"]).upper()
    for field, value in updates.items():
        setattr(org, field, value)
    await session.flush()
    await session.refresh(org)
    return org


@router.get("/me/members", response_model=MemberListResponse)
async def list_my_organisation_members(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MemberListResponse:
    await _load_caller_org(session, auth)
    result = await session.execute(
        select(User)
        .where(User.org_id == auth.org_id)
        .order_by(User.created_at.asc())
    )
    members = list(result.scalars().all())
    return MemberListResponse(
        members=[MemberResponse.model_validate(member) for member in members]
    )


@router.post(
    "/me/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=InviteStubResponse,
)
async def invite_member(
    body: InviteCreateRequest,
    auth: Annotated[AuthContext, Depends(require_roles("owner", "admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> InviteStubResponse:
    """Owner/admin only. Stub only — no invites table in §9.1 (see module docstring)."""
    await _load_caller_org(session, auth)
    return InviteStubResponse(
        status="stub_pending_schema",
        email=body.email.strip().lower(),
        role=body.role,
        invited_by_user_id=auth.user_id,
        detail=INVITES_SCHEMA_GAP_DETAIL,
    )


@router.delete(
    "/me/members/{user_id}",
    status_code=status.HTTP_200_OK,
)
async def remove_member(
    user_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_roles("owner", "admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    await _load_caller_org(session, auth)
    result = await session.execute(
        select(User).where(User.id == user_id, User.org_id == auth.org_id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found")

    if target.role == "owner":
        owner_count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.org_id == auth.org_id, User.role == "owner")
        )
        if int(owner_count or 0) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the only owner of the organisation",
            )

    await session.delete(target)
    await session.flush()
    return {"status": "removed", "user_id": str(user_id)}
