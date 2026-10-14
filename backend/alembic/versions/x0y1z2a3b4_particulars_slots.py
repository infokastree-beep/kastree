"""Nullable particulars slots on the year end. Existing rows stay NULL.

Revision ID: x0y1z2a3b4
Revises: w9x0y1z2a3
Create Date: 2026-10-14

Queue item 8. These are the slots that do not exist yet:

- related_party_particulars
- directors_remuneration_particulars
- loan_terms_particulars
- guarantee_particulars

Share classes already live on companies.share_classes. Post-balance-sheet
particulars already live on subsequent_events_particulars. This revision
does not add those again. There is no server default and no value
constraint. Existing rows stay NULL. This revision does not map the
columns, does not read them, and does not write them. Downgrade drops the
columns and reapplies least privilege. It does not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "x0y1z2a3b4"
down_revision: Union[str, None] = "w9x0y1z2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN related_party_particulars TEXT,
          ADD COLUMN directors_remuneration_particulars TEXT,
          ADD COLUMN loan_terms_particulars TEXT,
          ADD COLUMN guarantee_particulars TEXT
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP COLUMN IF EXISTS related_party_particulars,
          DROP COLUMN IF EXISTS directors_remuneration_particulars,
          DROP COLUMN IF EXISTS loan_terms_particulars,
          DROP COLUMN IF EXISTS guarantee_particulars
        """
    )
    op.execute(_PRIVILEGES.read_text())
