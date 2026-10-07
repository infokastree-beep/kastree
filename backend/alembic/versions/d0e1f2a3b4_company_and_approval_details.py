"""Company letterhead and this year's approval details.

Revision ID: d0e1f2a3b4
Revises: c9d0e1f2a3
Create Date: 2026-10-07

Nullable columns only. No new table. industry stays the Product 1 field.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d0e1f2a3b4"
down_revision: Union[str, None] = "c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          ADD COLUMN business_address TEXT,
          ADD COLUMN incorporated_on DATE,
          ADD COLUMN principal_activity TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN approval_date DATE,
          ADD COLUMN signing_directors JSONB
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP COLUMN IF EXISTS signing_directors,
          DROP COLUMN IF EXISTS approval_date
        """
    )
    op.execute(
        """
        ALTER TABLE companies
          DROP COLUMN IF EXISTS principal_activity,
          DROP COLUMN IF EXISTS incorporated_on,
          DROP COLUMN IF EXISTS business_address
        """
    )
