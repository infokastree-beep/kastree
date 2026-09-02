"""Current-user profile for the authenticated session."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import AuthContext, get_auth_context
from app.schemas.user import UserMeResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserMeResponse)
async def get_current_user(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> UserMeResponse:
    """Return the DB-backed role for the signed-in user (not the JWT role claim)."""
    return UserMeResponse(
        id=str(auth.user_id),
        org_id=str(auth.org_id),
        email=auth.email,
        role=auth.role,
    )
