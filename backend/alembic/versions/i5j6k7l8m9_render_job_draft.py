"""Draft Word export jobs. tb_version_id may be null.

Revision ID: i5j6k7l8m9
Revises: h4i5j6k7l8
Create Date: 2026-10-09

A render job may point at a draft instead of a trial-balance version.
findraft_draft_versions already has UNIQUE (id, org_id, company_id)
(findraft_draft_versions_id_org_company_key, from v2w3x4y5z6), so this
revision does not add that key.

Revision order:
  f2a3b4c5d6 -> g3h4i5j6k7 (#79) -> h4i5j6k7l8 (#81) -> i5j6k7l8m9 (this).

Downgrade drops the draft link and reapplies least privilege. It does
not GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "i5j6k7l8m9"
down_revision: Union[str, None] = "h4i5j6k7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_render_jobs
          ALTER COLUMN tb_version_id DROP NOT NULL,
          ADD COLUMN draft_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_render_jobs
          ADD CONSTRAINT findraft_render_jobs_source_check
          CHECK (tb_version_id IS NOT NULL OR draft_id IS NOT NULL)
        """
    )
    # The migration login may not hold REFERENCES. A superuser applies the
    # key. The unique key it targets already exists.
    op.execute(
        """
        DO $$
        BEGIN
          ALTER TABLE findraft_render_jobs
            ADD CONSTRAINT findraft_render_jobs_draft_fk
            FOREIGN KEY (draft_id, org_id, company_id)
            REFERENCES findraft_draft_versions (id, org_id, company_id)
            ON DELETE CASCADE;
        EXCEPTION
          WHEN insufficient_privilege THEN
            RAISE NOTICE
              'render job draft key skipped; REFERENCES is revoked';
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_render_jobs_draft_id
          ON findraft_render_jobs (draft_id)
        """
    )
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_findraft_render_jobs_draft_id")
    op.execute(
        """
        ALTER TABLE findraft_render_jobs
          DROP CONSTRAINT IF EXISTS findraft_render_jobs_draft_fk,
          DROP CONSTRAINT IF EXISTS findraft_render_jobs_source_check,
          DROP COLUMN IF EXISTS draft_id
        """
    )
    op.execute(
        """
        DELETE FROM findraft_render_jobs WHERE tb_version_id IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE findraft_render_jobs
          ALTER COLUMN tb_version_id SET NOT NULL
        """
    )
    op.execute(_PRIVILEGES.read_text())
