"""Current-user profile for the authenticated session."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import (
    AuthContext,
    get_db_session,
    is_platform_admin,
    require_client_admin,
    require_reader,
)
from app.schemas.audit import ErasureResponse
from app.schemas.user import Product2AccessResponse, UserMeResponse
from app.services.beta import beta_acknowledged, product2_grant_source
from app.services.erasure import ErasureRejected, erase_user
from app.services.retention import RETAINED_ON_ERASURE

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeResponse)
async def get_current_user(
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserMeResponse:
    """Return the DB-backed role for the signed-in user (not the JWT role claim)."""
    acknowledged = await beta_acknowledged(session, org_id=auth.org_id)
    source = (
        await product2_grant_source(session, org_id=auth.org_id)
        if acknowledged
        else None
    )
    platform_admin = is_platform_admin(auth)
    return UserMeResponse(
        id=str(auth.user_id),
        org_id=str(auth.org_id),
        email=auth.email,
        role=auth.role,
        is_platform_admin=platform_admin,
        product2_access=Product2AccessResponse(
            enabled=acknowledged or platform_admin,
            acknowledged=acknowledged,
            source=source,
            wording_signed_off=False,
        ),
    )


@router.post("/{user_id}/erasure", response_model=ErasureResponse)
async def erase_user_personal_data(
    user_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_client_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ErasureResponse:
    """Replace the user's email and login id. The user row and the audit log stay."""
    await aset_rls_org_id(session, auth.org_id)
    try:
        changed, statement = await erase_user(
            session,
            org_id=auth.org_id,
            actor_user_id=auth.user_id,
            actor_role=auth.role,
            target_user_id=user_id,
        )
    except ErasureRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return ErasureResponse(
        entity_type="user",
        entity_id=user_id,
        erased=changed,
        retained=list(RETAINED_ON_ERASURE),
        statement=statement,
    )
