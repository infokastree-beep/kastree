"""Database session and auth dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal, aset_rls_org_id
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_provisioning import organisation_id_for_clerk_org

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity for the current request."""

    clerk_user_id: str
    user_id: uuid.UUID
    org_id: uuid.UUID
    clerk_org_id: str
    role: str
    email: str


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify Clerk/MVP JWT and return claims.

    Local/MVP uses HS256 with auth_jwt_secret. Claims expected:
    sub (clerk user id), org_id (Clerk org id string), role, email (optional).
    """
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            options={"require": ["sub", "org_id"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession; commit on success."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_auth_context(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
    session: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """Verify JWT, resolve org/user, SET LOCAL app.current_org_id."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    claims = decode_access_token(credentials.credentials)
    clerk_user_id = str(claims["sub"])
    clerk_org_id = str(claims["org_id"])

    org_uuid_claim = claims.get("org_uuid")
    org_id = (
        uuid.UUID(str(org_uuid_claim))
        if org_uuid_claim
        else organisation_id_for_clerk_org(clerk_org_id)
    )
    await aset_rls_org_id(session, org_id)
    org = await session.get(Organisation, org_id)
    if org is None or org.clerk_org_id != clerk_org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown organisation",
        )

    result = await session.execute(
        select(User).where(
            User.clerk_user_id == clerk_user_id,
            User.org_id == org_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown user",
        )

    role = str(claims.get("role") or user.role)
    return AuthContext(
        clerk_user_id=clerk_user_id,
        user_id=user.id,
        org_id=org.id,
        clerk_org_id=org.clerk_org_id,
        role=role,
        email=user.email,
    )


async def get_db(
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_auth_context),
) -> AsyncSession:
    """Authenticated DB session with RLS org already set by get_auth_context."""
    await aset_rls_org_id(session, auth.org_id)
    return session
