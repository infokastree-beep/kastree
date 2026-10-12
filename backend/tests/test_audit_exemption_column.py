"""Revision r4s5t6u7v8 adds the claim columns. The model maps them."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "r4s5t6u7v8_audit_exemption_claim.py"
)
_MODEL = Path(__file__).resolve().parents[2] / "findraft" / "models" / "year_end.py"
_COLUMNS = (
    "audit_exemption_claimed",
    "audit_exemption_claimed_by_user_id",
    "audit_exemption_claimed_at",
)


def test_migration_adds_the_columns_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "r4s5t6u7v8"' in source
    assert 'down_revision: Union[str, None] = "q3r4s5t6u7"' in source
    assert "ADD COLUMN audit_exemption_claimed BOOLEAN" in source
    assert "ADD COLUMN audit_exemption_claimed_by_user_id UUID" in source
    assert "ADD COLUMN audit_exemption_claimed_at TIMESTAMPTZ" in source
    assert "findraft_year_ends_audit_exemption_claimed_by_fk" in source
    assert "idx_findraft_year_ends_audit_exemption_claimed_by" in source
    assert "DROP COLUMN IF EXISTS audit_exemption_claimed" in source
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
                    'audit_exemption_claimed',
                    'audit_exemption_claimed_by_user_id',
                    'audit_exemption_claimed_at'
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
                  AND indexname = 'idx_findraft_year_ends_audit_exemption_claimed_by'
                """
            )
        ).all()
    found = {row.column_name: row for row in rows}
    assert set(found) == set(_COLUMNS)
    claimed = found["audit_exemption_claimed"]
    assert claimed.is_nullable == "YES"
    assert claimed.column_default is None
    assert claimed.data_type == "boolean"
    actor = found["audit_exemption_claimed_by_user_id"]
    assert actor.is_nullable == "YES"
    assert actor.column_default is None
    assert actor.data_type == "uuid"
    claimed_at = found["audit_exemption_claimed_at"]
    assert claimed_at.is_nullable == "YES"
    assert claimed_at.column_default is None
    assert claimed_at.data_type == "timestamp with time zone"
    assert len(index) == 1
