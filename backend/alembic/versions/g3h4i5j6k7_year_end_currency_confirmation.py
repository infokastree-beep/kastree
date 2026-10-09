"""Currency acknowledgement on a year end. No amounts.

Revision ID: g3h4i5j6k7
Revises: f2a3b4c5d6
Create Date: 2026-10-09

Stores the currency code a member confirmed, who confirmed it, and when.
Existing rows stay null, so the V-CO-007 notice is unchanged until someone
confirms. Downgrade drops the columns and reapplies least privilege.
It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "g3h4i5j6k7"
down_revision: Union[str, None] = "f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN currency_confirmed_code VARCHAR(3),
          ADD COLUMN currency_confirmed_by_user_id UUID,
          ADD COLUMN currency_confirmed_at TIMESTAMPTZ
        """
    )
    # A login without REFERENCES on users cannot add this key. The owner
    # migration (CI superuser) does. The column still stores the user id.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_year_ends
            ADD CONSTRAINT findraft_year_ends_currency_confirmed_by_fk
            FOREIGN KEY (currency_confirmed_by_user_id)
            REFERENCES users (id);
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'currency confirmation user key skipped; REFERENCES on users is revoked';
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_year_ends_currency_confirmed_by
          ON findraft_year_ends (currency_confirmed_by_user_id)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_findraft_year_ends_currency_confirmed_by")
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP CONSTRAINT IF EXISTS findraft_year_ends_currency_confirmed_by_fk,
          DROP COLUMN IF EXISTS currency_confirmed_code,
          DROP COLUMN IF EXISTS currency_confirmed_by_user_id,
          DROP COLUMN IF EXISTS currency_confirmed_at
        """
    )
    op.execute(_PRIVILEGES.read_text())
