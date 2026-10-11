"""Compare the database Alembic revision with the code head.

A mismatch is reported. It does not stop the process from starting or from
answering /health.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app.db import AsyncSessionLocal

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SchemaRevision:
    database_revision: str | None
    code_revision: str | None
    revision_matches: bool


def code_heads() -> tuple[str, ...]:
    """Revision ids the code can migrate to. Empty when the scripts cannot be read."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(_BACKEND_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
        script = ScriptDirectory.from_config(config)
        return tuple(script.get_heads())
    except Exception:
        logger.warning("code_revision_unread")
        return ()


async def database_revisions() -> tuple[str, ...] | None:
    """Rows in alembic_version. None when the database cannot be read."""
    try:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(text("SELECT version_num FROM alembic_version"))
            return tuple(sorted(str(row[0]) for row in rows))
    except Exception:
        logger.warning("database_revision_unread")
        return None


def schema_revision(
    *,
    database: tuple[str, ...] | None,
    heads: tuple[str, ...],
) -> SchemaRevision:
    code = heads[0] if len(heads) == 1 else None
    stored = database[0] if database is not None and len(database) == 1 else None
    matches = (
        database is not None and len(heads) == 1 and set(database) == set(heads)
    )
    return SchemaRevision(
        database_revision=stored,
        code_revision=code,
        revision_matches=matches,
    )


async def current_schema_revision() -> SchemaRevision:
    return schema_revision(database=await database_revisions(), heads=code_heads())
