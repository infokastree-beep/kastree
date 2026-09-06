"""Copilot ask route — POST /trial-balances/{tb_id}/copilot.

Thin HTTP wrapper around ``ask_copilot()``. Auth + org RLS match variance/export.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.routers.trial_balances import _get_owned_tb
from app.schemas.copilot import CopilotAskRequest, CopilotAskResponse
from app.services.copilot_service import ask_copilot

router = APIRouter(prefix="/trial-balances", tags=["copilot"])


@router.post("/{tb_id}/copilot", response_model=CopilotAskResponse)
async def post_copilot_ask(
    tb_id: uuid.UUID,
    body: CopilotAskRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CopilotAskResponse:
    """Ask Copilot a question grounded in this trial balance's evidence."""
    await aset_rls_org_id(session, auth.org_id)
    # Ownership check (404 cross-org) before the orchestrator loads evidence.
    await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    question = body.question.strip()
    result = await ask_copilot(
        session,
        tb_id=tb_id,
        org_id=auth.org_id,
        user_id=auth.user_id,
        question=question,
    )
    grounded = result.grounded
    pack = result.pack
    return CopilotAskResponse(
        company_name=pack.company_name,
        period_end=pack.period_end,
        prior_period_end=pack.prior_period_end,
        answer_markdown=grounded.answer_markdown,
        citations=grounded.citations,
        confidence=grounded.confidence,
        refused=grounded.refused,
        refusal_message=grounded.refusal_message,
        dropped_sentence_count=grounded.dropped_sentence_count,
        turn_id=result.turn_id,
    )
