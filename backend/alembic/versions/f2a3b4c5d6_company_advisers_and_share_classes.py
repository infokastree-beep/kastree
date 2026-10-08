"""Advisers and share classes on the company. Not read by the application yet.

Revision ID: f2a3b4c5d6
Revises: e1f2a3b4c5
Create Date: 2026-10-08

Nullable JSON columns only. No new table. Application code must not select
these columns until this revision is applied. The grants repeat the
least-privilege set for companies: SELECT, INSERT, UPDATE, DELETE, and no
TRUNCATE, REFERENCES, or TRIGGER. Sequences are unchanged.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f2a3b4c5d6"
down_revision: Union[str, None] = "e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          ADD COLUMN advisers JSONB,
          ADD COLUMN share_classes JSONB
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.companies TO findraft"
    )
    op.execute(
        "REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public.companies FROM findraft"
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE companies
          DROP COLUMN IF EXISTS share_classes,
          DROP COLUMN IF EXISTS advisers
        """
    )
