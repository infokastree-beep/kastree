"""Revision w9x0y1z2a3 adds the compilation date and signatory. The model reads them."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "w9x0y1z2a3_compilation_report.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_COLUMNS = ("compilation_date", "compilation_signatory")


def test_migration_adds_the_columns_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "w9x0y1z2a3"' in source
    assert 'down_revision: Union[str, None] = "v8w9x0y1z2"' in source
    assert "ADD COLUMN compilation_date DATE" in source
    assert "ADD COLUMN compilation_signatory TEXT" in source
    for name in _COLUMNS:
        assert f"DROP COLUMN IF EXISTS {name}" in source
    assert "findraft_year_ends" in source
    assert "approval_date" not in executable
    assert "signing_directors" not in executable
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "CHECK" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    assert (
        "compilation_date: Mapped[date | None] = mapped_column(Date, nullable=True)"
        in model
    )
    assert (
        "compilation_signatory: Mapped[str | None] = mapped_column(Text, nullable=True)"
        in model
    )
    assert "approval_date" in model
    assert "signing_directors" in model


def test_code_head_is_the_compilation_report_revision() -> None:
    assert code_heads() == ("z2a3b4c5d6",)


def test_columns_are_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_year_ends'
                  AND column_name IN ('compilation_date', 'compilation_signatory')
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for row in found.values():
        assert row.is_nullable == "YES"
        assert row.column_default is None
    assert found["compilation_date"].data_type == "date"
    assert found["compilation_signatory"].data_type == "text"
