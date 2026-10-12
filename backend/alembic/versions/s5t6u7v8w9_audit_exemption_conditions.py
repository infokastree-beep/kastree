"""Nullable directors' confirmations on a year end. Existing rows stay NULL.

Revision ID: s5t6u7v8w9
Revises: r4s5t6u7v8
Create Date: 2026-10-12

Three booleans record the set: the company is not an excluded class, no
member notice was served, and annual returns were not filed late more than
once in five years. One user id and one timestamp record who confirmed the
set and when. There is no server default. This revision does not map the
columns, does not read them, and does not write them. Downgrade drops the
columns and reapplies least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "s5t6u7v8w9"
down_revision: Union[str, None] = "r4s5t6u7v8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN audit_exemption_not_excluded BOOLEAN,
          ADD COLUMN audit_exemption_no_member_notice BOOLEAN,
          ADD COLUMN audit_exemption_returns_not_late BOOLEAN,
          ADD COLUMN audit_exemption_conditions_by_user_id UUID,
          ADD COLUMN audit_exemption_conditions_at TIMESTAMPTZ
        """
    )
    # A login without REFERENCES on users cannot add this key. The owner
    # migration (CI superuser) does. The column still stores the user id.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_year_ends
            ADD CONSTRAINT findraft_year_ends_audit_exemption_conditions_by_fk
            FOREIGN KEY (audit_exemption_conditions_by_user_id)
            REFERENCES users (id);
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'audit exemption conditions user key skipped; REFERENCES on users is revoked';
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_year_ends_audit_exemption_conditions_by
          ON findraft_year_ends (audit_exemption_conditions_by_user_id)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_findraft_year_ends_audit_exemption_conditions_by"
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_audit_exemption_conditions_by_fk,
          DROP COLUMN IF EXISTS audit_exemption_not_excluded,
          DROP COLUMN IF EXISTS audit_exemption_no_member_notice,
          DROP COLUMN IF EXISTS audit_exemption_returns_not_late,
          DROP COLUMN IF EXISTS audit_exemption_conditions_by_user_id,
          DROP COLUMN IF EXISTS audit_exemption_conditions_at
        """
    )
    op.execute(_PRIVILEGES.read_text())
