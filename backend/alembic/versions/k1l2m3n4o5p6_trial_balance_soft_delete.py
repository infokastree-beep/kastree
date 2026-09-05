"""Add soft-delete columns to trial_balances + partial unique period index.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-09-05

Allows DELETE /trial-balances/{id} to soft-delete + archive while freeing the
(company_id, period_end) slot for a replacement upload (partial unique index).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trial_balances",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "trial_balances",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_trial_balances_company_deleted",
        "trial_balances",
        ["company_id", "is_deleted"],
        unique=False,
    )

    op.drop_constraint(
        "trial_balances_company_id_period_end_key",
        "trial_balances",
        type_="unique",
    )
    op.create_index(
        "trial_balances_company_id_period_end_active_key",
        "trial_balances",
        ["company_id", "period_end"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "trial_balances_company_id_period_end_active_key",
        table_name="trial_balances",
    )
    op.create_unique_constraint(
        "trial_balances_company_id_period_end_key",
        "trial_balances",
        ["company_id", "period_end"],
    )
    op.drop_index("idx_trial_balances_company_deleted", table_name="trial_balances")
    op.drop_column("trial_balances", "deleted_at")
    op.drop_column("trial_balances", "is_deleted")
