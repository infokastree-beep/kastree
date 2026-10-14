"""Nullable audit-exemption claim on a year end. Existing rows stay NULL.

Revision ID: r4s5t6u7v8
Revises: q3r4s5t6u7
Create Date: 2026-10-12

NULL means the position has not been recorded. True means claimed. False
means not claimed. There is no server default. This revision does not map
the columns, does not read them, and does not write them. Downgrade drops
the columns and reapplies least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "r4s5t6u7v8"
down_revision: Union[str, None] = "q3r4s5t6u7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN audit_exemption_claimed BOOLEAN,
          ADD COLUMN audit_exemption_claimed_by_user_id UUID,
          ADD COLUMN audit_exemption_claimed_at TIMESTAMPTZ
        """
    )
    # A login without REFERENCES on users cannot add this key. The owner
    # migration (CI superuser) does. The column still stores the user id.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_year_ends
            ADD CONSTRAINT findraft_year_ends_audit_exemption_claimed_by_fk
            FOREIGN KEY (audit_exemption_claimed_by_user_id)
            REFERENCES users (id);
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'audit exemption claim user key skipped; REFERENCES on users is revoked';
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_year_ends_audit_exemption_claimed_by
          ON findraft_year_ends (audit_exemption_claimed_by_user_id)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_findraft_year_ends_audit_exemption_claimed_by"
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_audit_exemption_claimed_by_fk,
          DROP COLUMN IF EXISTS audit_exemption_claimed,
          DROP COLUMN IF EXISTS audit_exemption_claimed_by_user_id,
          DROP COLUMN IF EXISTS audit_exemption_claimed_at
        """
    )
    op.execute(_PRIVILEGES.read_text())
