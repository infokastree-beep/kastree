"""Nullable comparative source on the year end. Existing rows stay NULL.

Revision ID: y1z2a3b4c5
Revises: x0y1z2a3b4
Create Date: 2026-10-14

Queue item 11. The design named p2q3r4s5t6 after n0o1p2q3r4. That revision
was never written. The head is x0y1z2a3b4, so this revision continues that
chain and does not fork it.

Columns, all nullable, no server default, no backfill:

- comparative_source, limited to product1_tb, first_period, manual, final_snapshot
- comparative_source_trial_balance_id, referencing trial_balances
- comparative_source_year_end_id, referencing findraft_year_ends
- comparative_source_draft_id
- comparative_source_sha256

This revision does not map the columns, does not read them, and does not
write them. Downgrade drops them and reapplies least privilege. It does
not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "y1z2a3b4c5"
down_revision: Union[str, None] = "x0y1z2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN comparative_source VARCHAR(32),
          ADD COLUMN comparative_source_trial_balance_id UUID,
          ADD COLUMN comparative_source_year_end_id UUID,
          ADD COLUMN comparative_source_draft_id UUID,
          ADD COLUMN comparative_source_sha256 VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD CONSTRAINT findraft_year_ends_comparative_source_check
          CHECK (
            comparative_source IS NULL
            OR comparative_source IN (
              'product1_tb', 'first_period', 'manual', 'final_snapshot'
            )
          )
        """
    )
    # A login without REFERENCES on trial_balances cannot add this key.
    # The owner migration (CI superuser) does. The column still stores the id.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_year_ends
            ADD CONSTRAINT findraft_year_ends_comparative_source_tb_fk
            FOREIGN KEY (comparative_source_trial_balance_id)
            REFERENCES trial_balances (id)
            ON DELETE SET NULL;
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'comparative source trial balance key skipped; REFERENCES on trial_balances is revoked';
        END $$;
        """
    )
    # The same REFERENCES revoke blocks a key back to this table.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_year_ends
            ADD CONSTRAINT findraft_year_ends_comparative_source_year_end_fk
            FOREIGN KEY (comparative_source_year_end_id)
            REFERENCES findraft_year_ends (id)
            ON DELETE SET NULL;
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'comparative source year end key skipped; REFERENCES on findraft_year_ends is revoked';
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_year_ends_comparative_source_tb
          ON findraft_year_ends (comparative_source_trial_balance_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_year_ends_comparative_source_year_end
          ON findraft_year_ends (comparative_source_year_end_id)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_findraft_year_ends_comparative_source_tb"
    )
    op.execute(
        "DROP INDEX IF EXISTS idx_findraft_year_ends_comparative_source_year_end"
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_comparative_source_check,
          DROP CONSTRAINT IF EXISTS findraft_year_ends_comparative_source_tb_fk,
          DROP CONSTRAINT IF EXISTS findraft_year_ends_comparative_source_year_end_fk,
          DROP COLUMN IF EXISTS comparative_source,
          DROP COLUMN IF EXISTS comparative_source_trial_balance_id,
          DROP COLUMN IF EXISTS comparative_source_year_end_id,
          DROP COLUMN IF EXISTS comparative_source_draft_id,
          DROP COLUMN IF EXISTS comparative_source_sha256
        """
    )
    op.execute(_PRIVILEGES.read_text())
