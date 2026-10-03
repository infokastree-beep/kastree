"""Remember a confirmed statutory sub-line on the Product 1 mapping.

Revision ID: b8c9d0e1f2
Revises: a7b8c9d0e1
Create Date: 2026-10-03

The Product 1 canonical_line stays unchanged. statutory_line is the engine
line the accountant confirmed for that company, code, and name.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b8c9d0e1f2"
down_revision: Union[str, None] = "a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE account_mappings
          ADD COLUMN statutory_line VARCHAR(64)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE account_mappings
          DROP COLUMN IF EXISTS statutory_line
        """
    )
