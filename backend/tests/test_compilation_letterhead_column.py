"""Revision v8w9x0y1z2 adds the practice letterhead. The model maps it."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "v8w9x0y1z2_compilation_letterhead.py"
)
_MODEL = Path(__file__).resolve().parents[1] / "app" / "models" / "organisation.py"
_COLUMNS = ("letterhead_address", "letterhead_contact")


def test_migration_adds_the_columns_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "v8w9x0y1z2"' in source
    assert 'down_revision: Union[str, None] = "u7v8w9x0y1"' in source
    for name in _COLUMNS:
        assert f"ADD COLUMN {name} " in source
        assert f"DROP COLUMN IF EXISTS {name}" in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "CHECK" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    for name in _COLUMNS:
        assert (
            f"{name}: Mapped[str | None] = mapped_column(Text, nullable=True)" in model
        )


def test_code_head_is_the_compilation_letterhead_revision() -> None:
    assert code_heads() == ("x0y1z2a3b4",)


def test_columns_are_nullable_text_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'organisations'
                  AND column_name IN ('letterhead_address', 'letterhead_contact')
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for row in found.values():
        assert row.is_nullable == "YES"
        assert row.column_default is None
        assert row.data_type == "text"
