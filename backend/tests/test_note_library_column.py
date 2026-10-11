"""Revision m9n0o1p2q3 adds nullable note_library and does not read it."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "m9n0o1p2q3_draft_note_library.py"
)
_MODEL = (
    Path(__file__).resolve().parents[2] / "findraft" / "models" / "draft_version.py"
)


def test_migration_adds_the_column_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "m9n0o1p2q3"' in source
    assert 'down_revision: Union[str, None] = "l8m9n0o1p2"' in source
    assert "ADD COLUMN note_library JSONB" in source
    assert "DROP COLUMN IF EXISTS note_library" in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "country_of_incorporation" not in source
    assert "ALTER TABLE companies" not in source
    assert "SELECT" not in executable
    assert "note_library" not in _MODEL.read_text()


def test_code_head_is_the_note_library_revision() -> None:
    assert code_heads() == ("m9n0o1p2q3",)


def test_column_is_nullable_jsonb_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT is_nullable, column_default, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_draft_versions'
                  AND column_name = 'note_library'
                """
            )
        ).one()
    assert row.is_nullable == "YES"
    assert row.column_default is None
    assert row.data_type == "jsonb"
