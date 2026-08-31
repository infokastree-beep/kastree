"""Add waitlist_signups for public landing-page signups.

RLS: INSERT-only public policy (no SELECT) so the app role can record signups
without JWT while keeping rows private from normal query paths.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "waitlist_signups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("firm", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("approx_client_count", sa.String(), nullable=True),
        sa.Column("pain_point", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_waitlist_signups_email", "waitlist_signups", ["email"])

    op.execute("ALTER TABLE waitlist_signups ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY waitlist_signups_public_insert ON waitlist_signups
          FOR INSERT
          WITH CHECK (true)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS waitlist_signups_public_insert ON waitlist_signups"
    )
    op.drop_index("idx_waitlist_signups_email", table_name="waitlist_signups")
    op.drop_table("waitlist_signups")
