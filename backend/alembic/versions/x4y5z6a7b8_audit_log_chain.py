"""Product 2 Week 12: append-only audit log hash chain.

Revision ID: x4y5z6a7b8
Revises: w3x4y5z6a7
Create Date: 2026-10-01

The app role may insert and read. It may not update or delete. A trigger
refuses both even for the table owner. Erasure does not rewrite this table.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "x4y5z6a7b8"
down_revision: Union[str, None] = "w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE audit_logs
          ADD COLUMN chain_seq INTEGER NOT NULL,
          ADD COLUMN prev_hash VARCHAR(64) NOT NULL,
          ADD COLUMN row_hash VARCHAR(64) NOT NULL,
          ADD CONSTRAINT audit_logs_chain_key UNIQUE (org_id, chain_seq),
          ADD CONSTRAINT audit_logs_hash_length_check CHECK (
            char_length(prev_hash) = 64 AND char_length(row_hash) = 64
          )
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_audit_log_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          previous_hash text;
          previous_seq integer;
        BEGIN
          IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'audit log is append-only';
          END IF;
          SELECT row_hash, chain_seq INTO previous_hash, previous_seq
          FROM audit_logs
          WHERE org_id = NEW.org_id
          ORDER BY chain_seq DESC
          LIMIT 1;
          IF previous_hash IS NULL THEN
            IF NEW.chain_seq <> 1 OR NEW.prev_hash <> repeat('0', 64) THEN
              RAISE EXCEPTION 'audit log chain does not start at the genesis hash';
            END IF;
          ELSIF NEW.chain_seq <> previous_seq + 1
            OR NEW.prev_hash IS DISTINCT FROM previous_hash THEN
            RAISE EXCEPTION 'audit log chain does not link to the previous row';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_audit_log_append_only
        BEFORE INSERT OR UPDATE OR DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION findraft_audit_log_append_only();
        """
    )
    op.execute("DROP POLICY IF EXISTS audit_logs_org_isolation ON audit_logs")
    op.execute(
        """
        CREATE POLICY audit_logs_org_isolation
          ON audit_logs
          FOR ALL
          USING (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
          WITH CHECK (
            org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid
          )
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_app') THEN
            GRANT SELECT, INSERT ON audit_logs TO findraft_app;
            REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS findraft_audit_log_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS findraft_audit_log_append_only()")
    op.execute("DROP POLICY IF EXISTS audit_logs_org_isolation ON audit_logs")
    op.execute(
        """
        CREATE POLICY audit_logs_org_isolation ON audit_logs
          FOR ALL
          USING (org_id = current_setting('app.current_org_id')::UUID)
        """
    )
    op.execute(
        """
        ALTER TABLE audit_logs
          DROP CONSTRAINT IF EXISTS audit_logs_hash_length_check,
          DROP CONSTRAINT IF EXISTS audit_logs_chain_key,
          DROP COLUMN IF EXISTS row_hash,
          DROP COLUMN IF EXISTS prev_hash,
          DROP COLUMN IF EXISTS chain_seq
        """
    )
