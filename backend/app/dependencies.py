"""Database session and auth dependencies.

JWT verification policy (algorithm confusion):
- Request auth (``get_auth_context`` → ``decode_access_token``) verifies **only**
  Clerk session JWTs with a fixed ``algorithms=["RS256"]`` against Clerk JWKS.
  It never accepts HS256 and never lets the token's ``alg`` header choose the
  algorithm list.
- HS256 + ``AUTH_JWT_SECRET`` lives in ``decode_test_hs256_token`` only. That
  function is not called from ``get_auth_context``. Pytest installs a monkeypatch
  so the ASGI test client can present fixtures minted by ``make_access_token``;
  production/staging/development request paths never take that branch.
"""

from __future__ import annotations

import base64
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal, aset_rls_org_id
from app.models.organisation import Organisation
from app.models.user import User
from app.services.org_provisioning import organisation_id_for_clerk_org

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# Fixed algorithm lists — never derived from the token header.
_CLERK_JWT_ALGORITHMS: list[str] = ["RS256"]
_TEST_JWT_ALGORITHMS: list[str] = ["HS256"]


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity for the current request."""

    clerk_user_id: str
    user_id: uuid.UUID
    org_id: uuid.UUID
    clerk_org_id: str
    role: str
    email: str


def _clerk_frontend_api_from_publishable_key(publishable_key: str) -> str | None:
    """Decode Clerk publishable key → Frontend API host (e.g. foo-1.clerk.accounts.dev)."""
    try:
        raw = publishable_key.split("_", 2)[-1]
        padded = raw + "=" * (-len(raw) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        host = decoded.rstrip("$").strip()
        return host or None
    except Exception:
        return None


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    """Clerk JWKS client for RS256 session-token verification. Fail closed if unset."""
    url = settings.clerk_jwks_url
    if not url and settings.clerk_publishable_key:
        host = _clerk_frontend_api_from_publishable_key(settings.clerk_publishable_key)
        if host:
            url = f"https://{host}/.well-known/jwks.json"
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Clerk JWKS is not configured "
                "(set CLERK_JWKS_URL or CLERK_PUBLISHABLE_KEY)"
            ),
        )
    return PyJWKClient(url)


def _normalize_org_claim(claims: dict[str, Any]) -> dict[str, Any]:
    """Map Clerk's nested active-org claim onto a top-level ``org_id`` string.

    After RS256 (or test HS256) verification succeeds, claims are trusted payload
    fields from inside that verified JWT — never from headers/query/body.

    Sources considered, in order (first win):
    1. ``claims["org_id"]`` — custom JWT template / our test fixtures
    2. ``claims["o"]["id"]`` — Clerk Organizations session token shape
       (``o`` = active organization object; ``id`` = Clerk org id like ``org_…``)
    3. ``claims["orgId"]`` — alternate camelCase some templates use

    The value is always a Clerk organisation **string id**, not our internal UUID.
    """
    if claims.get("org_id"):
        return claims
    nested = claims.get("o")
    if isinstance(nested, dict) and nested.get("id"):
        return {**claims, "org_id": str(nested["id"])}
    if claims.get("orgId"):
        return {**claims, "org_id": str(claims["orgId"])}
    return claims


def _require_sub_and_org(claims: dict[str, Any]) -> dict[str, Any]:
    claims = _normalize_org_claim(claims)
    if "sub" not in claims or "org_id" not in claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Token missing required claims (sub, org_id). "
                "Activate a Clerk Organization and/or add org_id to the JWT template."
            ),
        )
    return claims


def decode_clerk_rs256_token(token: str) -> dict[str, Any]:
    """Verify a Clerk session JWT with a fixed RS256-only algorithm list.

    This is the only verification used by the request auth dependency in
    non-test processes. ``algorithms`` is the constant ``["RS256"]`` — never
    taken from the token header, and HS256 is not an accepted option here.
    """
    try:
        jwks = _jwks_client()
        signing_key = jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_CLERK_JWT_ALGORITHMS,  # fixed: ["RS256"] only
            options={"require": ["sub"]},
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        logger.info("Clerk JWKS RS256 verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    return _require_sub_and_org(claims)


def decode_test_hs256_token(token: str) -> dict[str, Any]:
    """HS256 verification for **pytest fixtures only**.

    Not referenced by ``get_auth_context``. Tests mint tokens with
    ``make_access_token`` and monkeypatch ``decode_access_token`` to this
    function for the duration of the test process. A real deployment never
    installs that patch, so a Bearer header on a live server cannot reach
    this path.
    """
    try:
        claims = jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=_TEST_JWT_ALGORITHMS,  # fixed: ["HS256"] only
            options={"require": ["sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    return _require_sub_and_org(claims)


def decode_access_token(token: str) -> dict[str, Any]:
    """Entry point used by ``get_auth_context``.

    Always RS256/Clerk JWKS in application code. Pytest replaces this symbol
    with ``decode_test_hs256_token`` via monkeypatch (see ``tests/conftest.py``).
    """
    return decode_clerk_rs256_token(token)


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
    """Verify JWT, resolve org/user, SET LOCAL app.current_org_id.

    Org identity for RLS:
    - ``clerk_org_id`` comes only from a cryptographically verified JWT claim
      (``org_id`` / normalised ``o.id``) via ``decode_access_token``.
    - Internal UUID is derived deterministically with
      ``organisation_id_for_clerk_org(clerk_org_id)`` — not from an
      untrusted header/query, and not from an optional ``org_uuid`` claim
      (that claim is ignored so a template cannot smuggle a different UUID).
    - DB row must exist and ``organisations.clerk_org_id`` must match the
      verified claim before RLS proceeds.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    claims = decode_access_token(credentials.credentials)
    clerk_user_id = str(claims["sub"])
    clerk_org_id = str(claims["org_id"])

    # Deterministic UUID from verified Clerk org id only — never from JWT org_uuid.
    org_id = organisation_id_for_clerk_org(clerk_org_id)
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

    # Authoritative role is always the DB row — never trust a JWT role claim for authz.
    return AuthContext(
        clerk_user_id=clerk_user_id,
        user_id=user.id,
        org_id=org.id,
        clerk_org_id=org.clerk_org_id,
        role=user.role,
        email=user.email,
    )


def platform_admin_email_allowlist() -> frozenset[str]:
    """Parsed PLATFORM_ADMIN_EMAILS — lowercase, trimmed, empty entries dropped."""
    raw = settings.platform_admin_emails or ""
    return frozenset(
        part.strip().lower() for part in raw.split(",") if part.strip()
    )


def is_platform_admin_email(email: str) -> bool:
    return email.strip().lower() in platform_admin_email_allowlist()


def require_roles(*allowed_roles: str):
    """FastAPI dependency factory: 403 unless auth.role is in allowed_roles (§8.2).

    Reusable pattern for owner/admin-only endpoints (invites, member removal, …).
    """

    allowed = frozenset(allowed_roles)

    async def _dependency(
        auth: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        if auth.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this resource.",
            )
        return auth

    return _dependency


def require_platform_admin():
    """Owner role plus PLATFORM_ADMIN_EMAILS allowlist — not every org owner."""

    async def _dependency(
        auth: Annotated[AuthContext, Depends(require_roles("owner"))],
    ) -> AuthContext:
        if not is_platform_admin_email(auth.email):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this resource.",
            )
        return auth

    return _dependency


async def get_db(
    session: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_auth_context),
) -> AsyncSession:
    """Authenticated DB session with RLS org already set by get_auth_context."""
    await aset_rls_org_id(session, auth.org_id)
    return session
