"""Rename canonical_line accruals -> accruals_and_deferred_income.

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-02

Data migration for existing account_mappings rows (e.g. production test data on
JIE JIE LTD account 2100). Code allowlists and SOFP display use the new name.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'accruals_and_deferred_income'
        WHERE canonical_line = 'accruals'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE account_mappings
        SET canonical_line = 'accruals'
        WHERE canonical_line = 'accruals_and_deferred_income'
        """
    )
