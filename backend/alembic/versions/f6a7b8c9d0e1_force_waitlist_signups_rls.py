"""FORCE RLS on waitlist_signups so the findraft app role cannot SELECT rows.

Without FORCE, the table owner bypasses RLS policies and any ORM query could read
PII. INSERT-only policy remains the sole permitted operation for findraft.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE waitlist_signups FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE waitlist_signups NO FORCE ROW LEVEL SECURITY")
