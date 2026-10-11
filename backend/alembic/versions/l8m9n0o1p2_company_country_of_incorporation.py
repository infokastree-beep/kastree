"""Nullable country of incorporation. Existing companies stay NULL.

Revision ID: l8m9n0o1p2
Revises: k7l8m9n0o1
Create Date: 2026-10-11

Adds companies.country_of_incorporation. There is no default. Existing rows
stay NULL. Downgrade drops the column and reapplies least privilege. It does
not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "l8m9n0o1p2"
down_revision: Union[str, None] = "k7l8m9n0o1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          ADD COLUMN country_of_incorporation VARCHAR(2)
        """
    )
    op.execute(
        """
        ALTER TABLE companies
          ADD CONSTRAINT companies_country_of_incorporation_check
          CHECK (
            country_of_incorporation IS NULL
            OR country_of_incorporation ~ '^[A-Z]{2}$'
          )
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          DROP CONSTRAINT IF EXISTS companies_country_of_incorporation_check,
          DROP COLUMN IF EXISTS country_of_incorporation
        """
    )
    op.execute(_PRIVILEGES.read_text())
