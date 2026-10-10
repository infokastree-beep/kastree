"""Product 2 acknowledgement columns on organisations.

Revision ID: k7l8m9n0o1
Revises: j6k7l8m9n0
Create Date: 2026-10-10

Adds the current-state columns for a practice beta acknowledgement.
Existing organisations stay null unless a beta_self_review audit row already
exists. That backfill copies the earliest row's time and user, and it does
not overwrite a timestamp that is already set. Audit rows are not rewritten.

The backfill reads every practice, so it runs only for a superuser or
BYPASSRLS role. Row level security would hide other practices from findraft.

Downgrade drops the columns and reapplies least privilege. It does not
GRANT ALL. The audit history stays.

On 10 October 2026 the agent database (local findraft_dev) had 0
beta_self_review rows. Production Postgres was not reachable from that
environment, so confirm the production rows before running this revision.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "k7l8m9n0o1"
down_revision: Union[str, None] = "j6k7l8m9n0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)

BACKFILL_SQL = """
UPDATE organisations AS practice
SET
  product2_acknowledged_at = earliest.created_at,
  product2_acknowledged_by_user_id = (
    SELECT users.id FROM users WHERE users.id = earliest.user_id
  )
FROM (
  SELECT DISTINCT ON (audit_logs.org_id)
    audit_logs.org_id,
    audit_logs.created_at,
    audit_logs.user_id
  FROM audit_logs
  WHERE audit_logs.action = 'beta_self_review'
  ORDER BY audit_logs.org_id, audit_logs.created_at ASC, audit_logs.chain_seq ASC
) AS earliest
WHERE practice.id = earliest.org_id
  AND practice.product2_acknowledged_at IS NULL
"""


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE organisations
          ADD COLUMN product2_acknowledged_at TIMESTAMPTZ,
          ADD COLUMN product2_acknowledged_by_user_id UUID
        """
    )
    # A login without REFERENCES on users cannot add this key. The owner
    # migration (CI superuser) does. The column still stores the user id.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE organisations
            ADD CONSTRAINT organisations_product2_acknowledged_by_fk
            FOREIGN KEY (product2_acknowledged_by_user_id)
            REFERENCES users (id)
            ON DELETE SET NULL;
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'product2 acknowledgement user key skipped; REFERENCES on users is revoked';
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX idx_organisations_product2_acknowledged_by
          ON organisations (product2_acknowledged_by_user_id)
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
          bypass boolean;
        BEGIN
          SELECT rolsuper OR rolbypassrls INTO bypass
          FROM pg_roles
          WHERE rolname = current_user;
          IF NOT COALESCE(bypass, false) THEN
            RAISE EXCEPTION
              'product2 acknowledgement backfill must run as a superuser or BYPASSRLS role so every practice is visible';
          END IF;
        END $$;
        """
    )
    op.execute(BACKFILL_SQL)
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_organisations_product2_acknowledged_by"
    )
    op.execute(
        """
        ALTER TABLE organisations
          DROP CONSTRAINT IF EXISTS organisations_product2_acknowledged_by_fk,
          DROP COLUMN IF EXISTS product2_acknowledged_at,
          DROP COLUMN IF EXISTS product2_acknowledged_by_user_id
        """
    )
    op.execute(_PRIVILEGES.read_text())
