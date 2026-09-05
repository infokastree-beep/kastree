"""Add company_type + materiality_suggestion_dismissed_at on companies.

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-09-05

Supports ISA 320-style materiality auto-suggestion (trading vs holding)
and a soft-dismiss flag for the statements-dashboard banner.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l2m3n4o5p6q7"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "company_type",
            sa.String(),
            server_default=sa.text("'trading'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "companies_company_type_check",
        "companies",
        "company_type IN ('trading', 'holding')",
    )
    op.add_column(
        "companies",
        sa.Column(
            "materiality_suggestion_dismissed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "materiality_suggestion_dismissed_at")
    op.drop_constraint(
        "companies_company_type_check",
        "companies",
        type_="check",
    )
    op.drop_column("companies", "company_type")
