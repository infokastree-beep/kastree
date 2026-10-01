"""Product 2 Week 6: confirmed statutory mappings.

Revision ID: u1v2w3x4y5
Revises: t0u1v2w3x4
Create Date: 2026-10-01

Confirmed mappings are insert-only. A new trial-balance version is how a
practice changes them. Unconfirmed suggestions are not stored here.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "u1v2w3x4y5"
down_revision: Union[str, None] = "t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY = """
          USING (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
          WITH CHECK (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
"""


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_tb_versions
          ADD CONSTRAINT findraft_tb_versions_id_org_company_key
          UNIQUE (id, org_id, company_id)
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_confirmed_mappings (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          tb_version_id UUID NOT NULL,
          nominal_code VARCHAR(64) NOT NULL,
          canonical_line VARCHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_confirmed_mappings_code_key
            UNIQUE (tb_version_id, nominal_code),
          CONSTRAINT findraft_confirmed_mappings_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_confirmed_mappings_version_fk
            FOREIGN KEY (tb_version_id, org_id, company_id)
            REFERENCES findraft_tb_versions (id, org_id, company_id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_confirmed_mappings_org_id
          ON findraft_confirmed_mappings (org_id)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_confirmed_mappings_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'confirmed mapping is immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_confirmed_mappings_immutable
        BEFORE UPDATE OR DELETE ON findraft_confirmed_mappings
        FOR EACH ROW
        EXECUTE FUNCTION findraft_confirmed_mappings_immutable();
        """
    )
    op.execute(
        "ALTER TABLE findraft_confirmed_mappings ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "ALTER TABLE findraft_confirmed_mappings FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        f"""
        CREATE POLICY findraft_confirmed_mappings_org_isolation
          ON findraft_confirmed_mappings
          FOR ALL
          {_POLICY}
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_app') THEN
            GRANT SELECT, INSERT ON findraft_confirmed_mappings TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_confirmed_mappings_immutable "
        "ON findraft_confirmed_mappings"
    )
    op.execute("DROP TABLE IF EXISTS findraft_confirmed_mappings")
    op.execute("DROP FUNCTION IF EXISTS findraft_confirmed_mappings_immutable()")
    op.execute(
        "ALTER TABLE findraft_tb_versions "
        "DROP CONSTRAINT IF EXISTS findraft_tb_versions_id_org_company_key"
    )
