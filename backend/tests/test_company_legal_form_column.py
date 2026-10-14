"""Revision t6u7v8w9x0 adds companies.legal_form. The model maps it."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "t6u7v8w9x0_company_legal_form.py"
)
_MODEL = Path(__file__).resolve().parents[1] / "app" / "models" / "company.py"


def test_migration_adds_the_column_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "t6u7v8w9x0"' in source
    assert 'down_revision: Union[str, None] = "s5t6u7v8w9"' in source
    assert "ADD COLUMN legal_form VARCHAR(64)" in source
    assert "DROP COLUMN IF EXISTS legal_form" in source
    assert "company_type" not in source
    assert "CHECK" not in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    column = model.split("legal_form:", 1)[1].split("industry:", 1)[0]
    assert "Mapped[str | None]" in column
    assert "String(64)" in column
    assert "nullable=True" in column
    assert "server_default" not in column


def test_code_head_is_the_company_legal_form_revision() -> None:
    assert code_heads() == ("x0y1z2a3b4",)


def test_column_is_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT is_nullable, column_default, data_type, character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'companies'
                  AND column_name = 'legal_form'
                """
            )
        ).one()
    assert row.is_nullable == "YES"
    assert row.column_default is None
    assert row.data_type == "character varying"
    assert row.character_maximum_length == 64
