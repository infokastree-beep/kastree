"""POST /commentary/feedback — thumbs + optional correction (§10.2 / §7)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.client import Client
from app.models.commentary_feedback import CommentaryFeedback
from app.models.trial_balance import TrialBalance
from app.models.variance_analysis import VarianceAnalysis
from app.schemas.commentary import (
    CommentaryFeedbackRequest,
    CommentaryFeedbackResponse,
    CommentaryRecord,
    VarianceCommentaryResult,
)

router = APIRouter(prefix="/commentary", tags=["commentary"])


async def _get_owned_variance(
    session: AsyncSession,
    *,
    variance_id: uuid.UUID,
    org_id: uuid.UUID,
) -> VarianceAnalysis:
    """Variance via TB → client → org; 404 cross-org (not 403)."""
    result = await session.execute(
        select(VarianceAnalysis)
        .join(TrialBalance, TrialBalance.id == VarianceAnalysis.tb_id)
        .join(Client, Client.id == TrialBalance.client_id)
        .where(
            VarianceAnalysis.id == variance_id,
            Client.org_id == org_id,
            Client.is_deleted.is_(False),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Variance analysis not found")
    return row


def _apply_corrected_commentary(
    variance: VarianceAnalysis,
    *,
    line_item_code: str,
    corrected_text: str,
    editor_user_id: uuid.UUID,
) -> None:
    """Update variance_analyses.commentary; preserve original AI text (§7 / §4.3)."""
    raw: dict[str, Any] = dict(variance.commentary or {})
    if "commentaries" in raw and isinstance(raw["commentaries"], dict):
        commentaries: dict[str, Any] = dict(raw["commentaries"])
    else:
        # Treat a flat line_item_code map as commentaries.
        commentaries = {k: v for k, v in raw.items() if isinstance(v, dict)}

    existing_raw = commentaries.get(line_item_code)
    if isinstance(existing_raw, dict):
        existing = CommentaryRecord.model_validate(existing_raw)
        # Keep the first original AI wording across repeated edits.
        original = existing.original_text if existing.is_edited and existing.original_text else existing.text
        updated = existing.model_copy(
            update={
                "text": corrected_text,
                "is_edited": True,
                "edited_by_user_id": editor_user_id,
                "original_text": original,
            }
        )
    else:
        updated = CommentaryRecord(
            text=corrected_text,
            is_ai_generated=False,
            is_edited=True,
            reasoning="",
            confidence="low",
            edited_by_user_id=editor_user_id,
            original_text=None,
        )

    commentaries[line_item_code] = updated.model_dump(mode="json", exclude_none=True)
    result = VarianceCommentaryResult(
        commentaries={
            code: CommentaryRecord.model_validate(payload)
            for code, payload in commentaries.items()
        }
    )
    variance.commentary = result.to_jsonb()
    flag_modified(variance, "commentary")


@router.post(
    "/feedback",
    status_code=status.HTTP_201_CREATED,
    response_model=CommentaryFeedbackResponse,
)
async def submit_commentary_feedback(
    body: CommentaryFeedbackRequest,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CommentaryFeedbackResponse:
    await aset_rls_org_id(session, auth.org_id)
    variance = await _get_owned_variance(
        session, variance_id=body.variance_id, org_id=auth.org_id
    )

    if body.thumbs_up is None and not (body.corrected_text and body.corrected_text.strip()):
        raise HTTPException(
            status_code=400,
            detail="Provide thumbs_up and/or corrected_text",
        )

    corrected = body.corrected_text.strip() if body.corrected_text else None
    commentary_updated = False
    if corrected:
        _apply_corrected_commentary(
            variance,
            line_item_code=body.line_item_code,
            corrected_text=corrected,
            editor_user_id=auth.user_id,
        )
        commentary_updated = True

    feedback = CommentaryFeedback(
        variance_id=variance.id,
        user_id=auth.user_id,
        line_item_code=body.line_item_code,
        thumbs_up=body.thumbs_up,
        corrected_text=corrected,
    )
    session.add(feedback)
    await session.flush()
    await session.refresh(feedback)
    return CommentaryFeedbackResponse(
        id=feedback.id,
        variance_id=feedback.variance_id,
        user_id=feedback.user_id,
        line_item_code=feedback.line_item_code,
        thumbs_up=feedback.thumbs_up,
        corrected_text=feedback.corrected_text,
        created_at=feedback.created_at,
        commentary_updated=commentary_updated,
    )
