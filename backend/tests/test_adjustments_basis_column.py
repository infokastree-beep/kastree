"""Revision o1p2q3r4s5 adds the adjustments basis. The model does not map it."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db import SyncSessionLocal
from app.services.schema_revision import code_heads
from findraft.models.draft_version import DraftVersion

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "o1p2q3r4s5_adjustments_basis_trial_balance.py"
)
_MODEL = (
    Path(__file__).resolve().parents[2] / "findraft" / "models" / "draft_version.py"
)


def test_migration_adds_the_column_without_a_read_or_grant_all() -> None:
    source = _MIGRATION.read_text()
    executable = source.split('"""', 2)[-1]
    assert 'revision: str = "o1p2q3r4s5"' in source
    assert 'down_revision: Union[str, None] = "n0o1p2q3r4"' in source
    assert "ADD COLUMN adjustments_basis_trial_balance_id UUID" in source
    assert "DROP COLUMN IF EXISTS adjustments_basis_trial_balance_id" in source
    assert "REFERENCES trial_balances (id)" in source
    assert "ON DELETE SET NULL" in source
    assert "findraft_draft_versions_adjustments_basis_tb_fk" in source
    assert "CHECK" not in source
    assert "findraft_table_privileges.sql" in source
    assert "GRANT ALL" not in executable
    assert "SET DEFAULT" not in source
    assert "SELECT" not in executable
    model = _MODEL.read_text()
    assert "adjustments_basis_trial_balance_id" not in model
    assert "adjustments_basis_trial_balance_id" not in DraftVersion.__table__.columns


def test_code_head_is_the_adjustments_basis_revision() -> None:
    assert code_heads() == ("o1p2q3r4s5",)


def test_column_is_nullable_with_no_server_default() -> None:
    with SyncSessionLocal() as session:
        row = session.execute(
            text(
                """
                SELECT is_nullable, column_default, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'findraft_draft_versions'
                  AND column_name = 'adjustments_basis_trial_balance_id'
                """
            )
        ).one()
        key = session.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'findraft_draft_versions_adjustments_basis_tb_fk'
                """
            )
        ).scalar_one_or_none()
        can_reference = session.execute(
            text(
                """
                SELECT rolsuper OR has_table_privilege(
                  current_user, 'trial_balances', 'REFERENCES'
                )
                FROM pg_roles
                WHERE rolname = current_user
                """
            )
        ).scalar_one()
    assert row.is_nullable == "YES"
    assert row.column_default is None
    assert row.data_type == "uuid"
    if can_reference:
        assert key is not None
        assert "FOREIGN KEY (adjustments_basis_trial_balance_id)" in key
        assert "ON DELETE SET NULL" in key
    else:
        assert key is None
