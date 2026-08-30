"""Notifications API — per-user inbox (§10.2).

Ownership is against ``user_id`` (the caller), not org_id alone. Org membership
is still enforced via auth.org_id on the row, but listing/marking never returns
another user's notifications even in the same org.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.notification import Notification
from app.schemas.notification import (
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationListResponse,
    NotificationResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_DEFAULT_PAGE = 20
_MAX_PAGE = 100


async def _get_own_notification(
    session: AsyncSession,
    *,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Notification:
    """Per-user ownership — 404 if missing or belongs to another user (not 403)."""
    result = await session.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
            Notification.org_id == org_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return row


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE)] = _DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListResponse:
    await aset_rls_org_id(session, auth.org_id)
    # Filter by caller user_id — not org-wide inbox.
    base = select(Notification).where(
        Notification.user_id == auth.user_id,
        Notification.org_id == auth.org_id,
    )
    if unread_only:
        base = base.where(Notification.is_read.is_(False))

    total = await session.scalar(
        select(func.count()).select_from(base.subquery())
    )
    result = await session.execute(
        base.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    )
    items = list(result.scalars().all())
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.put("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_notification_read(
    notification_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MarkReadResponse:
    await aset_rls_org_id(session, auth.org_id)
    row = await _get_own_notification(
        session,
        notification_id=notification_id,
        user_id=auth.user_id,
        org_id=auth.org_id,
    )
    row.is_read = True
    await session.flush()
    return MarkReadResponse(id=row.id, is_read=True)


@router.put("/read-all", response_model=MarkAllReadResponse)
async def mark_all_notifications_read(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MarkAllReadResponse:
    await aset_rls_org_id(session, auth.org_id)
    result = await session.execute(
        update(Notification)
        .where(
            Notification.user_id == auth.user_id,
            Notification.org_id == auth.org_id,
            Notification.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await session.flush()
    return MarkAllReadResponse(updated_count=int(result.rowcount or 0))
