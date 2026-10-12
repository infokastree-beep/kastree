"""Revision s5t6u7v8w9 adds the confirmation columns. The model maps them."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "s5t6u7v8w9_audit_exemption_conditions.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_COLUMNS = (
    "audit_exemption_not_excluded",
    "audit_exemption_no_member_notice",
    "audit_exemption_returns_not_late",
    "audit_exemption_conditions_by_user_id",
    "audit_exemption_conditions_at",
)


def test_migration_adds_the_columns_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "s5t6u7v8w9"' in source
    assert 'down_revision: Union[str, None] = "r4s5t6u7v8"' in source
    assert "ADD COLUMN audit_exemption_not_excluded BOOLEAN" in source
    assert "ADD COLUMN audit_exemption_no_member_notice BOOLEAN" in source
    assert "ADD COLUMN audit_exemption_returns_not_late BOOLEAN" in source
    assert "ADD COLUMN audit_exemption_conditions_by_user_id UUID" in source
    assert "ADD COLUMN audit_exemption_conditions_at TIMESTAMPTZ" in source
    assert "findraft_year_ends_audit_exemption_conditions_by_fk" in source
    assert "idx_findraft_year_ends_audit_exemption_conditions_by" in source
    assert "DROP COLUMN IF EXISTS audit_exemption_not_excluded" in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    for name in _COLUMNS:
        assert name in model


def test_code_head_is_the_company_legal_form_revision() -> None:
    assert code_heads() == ("u7v8w9x0y1",)


def test_columns_are_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT column_name, is_nullable, column_default, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_year_ends'
                  AND column_name IN (
                    'audit_exemption_not_excluded',
                    'audit_exemption_no_member_notice',
                    'audit_exemption_returns_not_late',
                    'audit_exemption_conditions_by_user_id',
                    'audit_exemption_conditions_at'
                  )
                """
            )
        ).all()
        index = session.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = 'findraft_year_ends'
                  AND indexname = 'idx_findraft_year_ends_audit_exemption_conditions_by'
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    for name in (
        "audit_exemption_not_excluded",
        "audit_exemption_no_member_notice",
        "audit_exemption_returns_not_late",
    ):
        column = found[name]
        assert column.is_nullable == "YES"
        assert column.column_default is None
        assert column.data_type == "boolean"
    actor = found["audit_exemption_conditions_by_user_id"]
    assert actor.is_nullable == "YES"
    assert actor.column_default is None
    assert actor.data_type == "uuid"
    confirmed_at = found["audit_exemption_conditions_at"]
    assert confirmed_at.is_nullable == "YES"
    assert confirmed_at.column_default is None
    assert confirmed_at.data_type == "timestamp with time zone"
    assert len(index) == 1
