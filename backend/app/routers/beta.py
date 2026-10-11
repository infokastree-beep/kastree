"""First-practice beta. Every role can read the position. An admin records it."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import (
    AuthContext,
    get_db_session,
    require_client_admin,
    require_reader,
)
from app.schemas.beta import (
    BetaAcknowledgementRequest,
    BetaAcknowledgementResponse,
    BetaPositionResponse,
)
from app.services.beta import (
    BETA_STATEMENT,
    PACK_ID,
    acknowledge_beta_self_review,
    beta_acknowledged,
)

router = APIRouter(
    prefix="/beta",
    tags=["beta"],
)


@router.get("", response_model=BetaPositionResponse)
async def get_beta_position(
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BetaPositionResponse:
    await aset_rls_org_id(session, auth.org_id)
    acknowledged = await beta_acknowledged(session, org_id=auth.org_id)
    return BetaPositionResponse(
        pack_id=PACK_ID,
        wording_signed_off=False,
        self_review_required=True,
        filing_included=False,
        acknowledged=acknowledged,
        statement=BETA_STATEMENT,
    )


@router.post("/acknowledgement", response_model=BetaAcknowledgementResponse)
async def post_beta_acknowledgement(
    body: BetaAcknowledgementRequest,
    auth: Annotated[AuthContext, Depends(require_client_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BetaAcknowledgementResponse:
    del body
    await aset_rls_org_id(session, auth.org_id)
    recorded = await acknowledge_beta_self_review(
        session,
        org_id=auth.org_id,
        actor_user_id=auth.user_id,
    )
    return BetaAcknowledgementResponse(
        recorded=recorded,
        acknowledged=True,
        wording_signed_off=False,
        filing_included=False,
        statement=BETA_STATEMENT,
    )
