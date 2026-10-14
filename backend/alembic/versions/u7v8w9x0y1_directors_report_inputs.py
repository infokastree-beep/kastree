"""Nullable directors' report inputs on a year end. Existing rows stay NULL.

Revision ID: u7v8w9x0y1
Revises: t6u7v8w9x0
Create Date: 2026-10-12

Adds the typed facts the directors' report does not already store.
Companies Act 2014, sections 326, 328 and 329, and section 288 for the
period-length notice. There is no server default and no value constraint.
Existing rows stay NULL. This revision does not map the columns, does not
read them, and does not write them. Downgrade drops the columns and
reapplies least privilege. It does not GRANT ALL.

Directors who served and principal activities stay on the company.
Own-share and subsequent-event yes/no answers stay on the disclosure
flags. Business review, principal risks and future developments stay
optional for a small company and have no column.

share_interests, once mapped, is a list of objects:
{"name", "role" (director or secretary), "at_end", "at_start"}.
Each end is {"interested": true or false, "holdings": [...]}.
A holding is {"undertaking", "shares", "amount"}.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "u7v8w9x0y1"
down_revision: Union[str, None] = "t6u7v8w9x0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN accounting_records_location TEXT,
          ADD COLUMN interim_dividend NUMERIC(19, 2),
          ADD COLUMN recommended_dividend NUMERIC(19, 2),
          ADD COLUMN share_interests JSONB,
          ADD COLUMN own_shares_particulars TEXT,
          ADD COLUMN subsequent_events_particulars TEXT,
          ADD COLUMN research_development_relevant BOOLEAN,
          ADD COLUMN research_development_detail TEXT,
          ADD COLUMN political_donations_relevant BOOLEAN,
          ADD COLUMN political_donations_detail TEXT,
          ADD COLUMN accounting_period_change_filed BOOLEAN
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          DROP COLUMN IF EXISTS accounting_records_location,
          DROP COLUMN IF EXISTS interim_dividend,
          DROP COLUMN IF EXISTS recommended_dividend,
          DROP COLUMN IF EXISTS share_interests,
          DROP COLUMN IF EXISTS own_shares_particulars,
          DROP COLUMN IF EXISTS subsequent_events_particulars,
          DROP COLUMN IF EXISTS research_development_relevant,
          DROP COLUMN IF EXISTS research_development_detail,
          DROP COLUMN IF EXISTS political_donations_relevant,
          DROP COLUMN IF EXISTS political_donations_detail,
          DROP COLUMN IF EXISTS accounting_period_change_filed
        """
    )
    op.execute(_PRIVILEGES.read_text())
