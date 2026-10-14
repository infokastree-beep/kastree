"""Nullable adjustments basis on a draft. Existing rows stay NULL.

Revision ID: o1p2q3r4s5
Revises: n0o1p2q3r4
Create Date: 2026-10-14

Queue item 12. findraft_draft_versions.adjustments_basis_trial_balance_id
UUID NULL, referencing trial_balances. No server default. No backfill.
No check constraint. A null means no notice. This revision does not map
the column, does not read it, and does not write it. Upgrade and
downgrade reapply least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "o1p2q3r4s5"
down_revision: Union[str, None] = "n0o1p2q3r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          ADD COLUMN adjustments_basis_trial_balance_id UUID
        """
    )
    # A login without REFERENCES on trial_balances cannot add this key.
    # The owner migration does. The column still stores the id.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_draft_versions
            ADD CONSTRAINT findraft_draft_versions_adjustments_basis_tb_fk
            FOREIGN KEY (adjustments_basis_trial_balance_id)
            REFERENCES trial_balances (id)
            ON DELETE SET NULL;
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'adjustments basis key skipped; REFERENCES on trial_balances is revoked';
        END $$;
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          DROP CONSTRAINT IF EXISTS findraft_draft_versions_adjustments_basis_tb_fk,
          DROP COLUMN IF EXISTS adjustments_basis_trial_balance_id
        """
    )
    op.execute(_PRIVILEGES.read_text())
