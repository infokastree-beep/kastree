"""SQLAlchemy engines and session helpers (sync + async)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings

sync_engine = create_engine(settings.database_url_sync, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# Async engine: NullPool avoids cross-event-loop connection reuse under pytest-asyncio.
async_engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    poolclass=NullPool,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def set_rls_org_id(session: Session, org_id: uuid.UUID) -> None:
    """SET LOCAL app.current_org_id for the current transaction (sync)."""
    session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )


async def aset_rls_org_id(session: AsyncSession, org_id: uuid.UUID) -> None:
    """SET LOCAL app.current_org_id for the current transaction (async)."""
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )


async def aset_platform_admin(session: AsyncSession) -> None:
    """SET LOCAL app.platform_admin for cross-tenant Owner admin reads (async).

    Requires app.current_org_id to already be set in this transaction (via
    get_auth_context). Setting platform_admin alone can error on
    organisations_self_isolation's UUID cast if current_org_id is missing.
    """
    await session.execute(text("SELECT set_config('app.platform_admin', 'true', true)"))


def get_sync_session() -> Generator[Session, None, None]:
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
