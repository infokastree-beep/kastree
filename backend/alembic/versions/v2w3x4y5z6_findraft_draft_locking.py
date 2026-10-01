"""Product 2 Week 10: draft locking, adjustments, disclosure answers.

Revision ID: v2w3x4y5z6
Revises: u1v2w3x4y5
Create Date: 2026-10-01

Note overrides and text blocks are not created. The lock trigger covers
adjustment journals, their lines, disclosure answers, and confirmed mappings.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "v2w3x4y5z6"
down_revision: Union[str, None] = "u1v2w3x4y5"
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


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_org_isolation
          ON {table}
          FOR ALL
          {_POLICY}
        """
    )


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          ADD COLUMN row_version INTEGER NOT NULL DEFAULT 1,
          ADD COLUMN snapshot JSONB,
          ADD COLUMN inputs_sha256 VARCHAR(64),
          ADD COLUMN engine_sha VARCHAR(64),
          ADD COLUMN finalised_by_user_id UUID REFERENCES users (id),
          ADD CONSTRAINT findraft_draft_versions_id_org_company_key
            UNIQUE (id, org_id, company_id),
          ADD CONSTRAINT findraft_draft_versions_final_snapshot_check
            CHECK (
              status <> 'final'
              OR (
                snapshot IS NOT NULL
                AND inputs_sha256 IS NOT NULL
                AND engine_sha IS NOT NULL
              )
            )
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_draft_status_guard()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF OLD.status = 'final' AND (
            NEW.status IS DISTINCT FROM OLD.status
            OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
            OR NEW.inputs_sha256 IS DISTINCT FROM OLD.inputs_sha256
            OR NEW.engine_sha IS DISTINCT FROM OLD.engine_sha
            OR NEW.pack_id IS DISTINCT FROM OLD.pack_id
            OR NEW.pack_version IS DISTINCT FROM OLD.pack_version
          ) THEN
            RAISE EXCEPTION 'FINAL draft is immutable';
          END IF;
          IF OLD.status = 'locked' AND NEW.status NOT IN ('locked', 'final') THEN
            RAISE EXCEPTION 'locked draft cannot return to draft';
          END IF;
          IF NEW.row_version < OLD.row_version THEN
            RAISE EXCEPTION 'row_version cannot decrease';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_draft_status_guard
        BEFORE UPDATE ON findraft_draft_versions
        FOR EACH ROW
        EXECUTE FUNCTION findraft_draft_status_guard();
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_refuse_locked_draft_child()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent_status text;
          draft_id uuid;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            draft_id := OLD.draft_version_id;
          ELSE
            draft_id := NEW.draft_version_id;
          END IF;
          SELECT status INTO parent_status
          FROM findraft_draft_versions
          WHERE id = draft_id;
          IF parent_status IN ('locked', 'final') THEN
            RAISE EXCEPTION 'draft is %; writes are refused', parent_status;
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_refuse_mapping_on_locked_draft()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM findraft_draft_versions
            WHERE tb_version_id = NEW.tb_version_id
              AND status IN ('locked', 'final')
          ) THEN
            RAISE EXCEPTION 'draft is locked or final; mapping writes are refused';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_confirmed_mappings_locked_draft
        BEFORE INSERT ON findraft_confirmed_mappings
        FOR EACH ROW
        EXECUTE FUNCTION findraft_refuse_mapping_on_locked_draft();
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_adjustment_journals (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          draft_version_id UUID NOT NULL,
          narration VARCHAR(500) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_adjustment_journals_id_org_company_key
            UNIQUE (id, org_id, company_id),
          CONSTRAINT findraft_adjustment_journals_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_adjustment_journals_draft_fk
            FOREIGN KEY (draft_version_id, org_id, company_id)
            REFERENCES findraft_draft_versions (id, org_id, company_id)
            ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_adjustment_journals_org_id
          ON findraft_adjustment_journals (org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_adjustment_journals_draft_id
          ON findraft_adjustment_journals (draft_version_id)
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_adjustment_lines (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL,
          company_id UUID NOT NULL,
          journal_id UUID NOT NULL,
          draft_version_id UUID NOT NULL,
          line_no INTEGER NOT NULL,
          nominal_code VARCHAR(64) NOT NULL,
          account_name VARCHAR(255) NOT NULL,
          canonical_line VARCHAR(64) NOT NULL,
          debit NUMERIC(15, 2) NOT NULL,
          credit NUMERIC(15, 2) NOT NULL,
          CONSTRAINT findraft_adjustment_lines_number_key
            UNIQUE (journal_id, line_no),
          CONSTRAINT findraft_adjustment_lines_non_negative
            CHECK (debit >= 0 AND credit >= 0),
          CONSTRAINT findraft_adjustment_lines_one_side
            CHECK (
              (debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)
            ),
          CONSTRAINT findraft_adjustment_lines_journal_fk
            FOREIGN KEY (journal_id, org_id, company_id)
            REFERENCES findraft_adjustment_journals (id, org_id, company_id)
            ON DELETE CASCADE,
          CONSTRAINT findraft_adjustment_lines_draft_fk
            FOREIGN KEY (draft_version_id, org_id, company_id)
            REFERENCES findraft_draft_versions (id, org_id, company_id)
            ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_adjustment_lines_org_id
          ON findraft_adjustment_lines (org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_adjustment_lines_journal_id
          ON findraft_adjustment_lines (journal_id)
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_adjustment_journal_must_balance()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          jid uuid;
          debit_total numeric;
          credit_total numeric;
        BEGIN
          jid := COALESCE(NEW.journal_id, OLD.journal_id);
          SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
            INTO debit_total, credit_total
          FROM findraft_adjustment_lines
          WHERE journal_id = jid;
          IF debit_total <> credit_total THEN
            RAISE EXCEPTION 'adjustment journal does not balance';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER findraft_adjustment_journal_must_balance
        AFTER INSERT OR UPDATE OR DELETE ON findraft_adjustment_lines
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION findraft_adjustment_journal_must_balance();
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_adjustment_journals_locked_draft
        BEFORE INSERT OR UPDATE OR DELETE ON findraft_adjustment_journals
        FOR EACH ROW
        EXECUTE FUNCTION findraft_refuse_locked_draft_child();
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_adjustment_lines_locked_draft
        BEFORE INSERT OR UPDATE OR DELETE ON findraft_adjustment_lines
        FOR EACH ROW
        EXECUTE FUNCTION findraft_refuse_locked_draft_child();
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_disclosure_answers (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          draft_version_id UUID NOT NULL,
          flag_name VARCHAR(64) NOT NULL,
          answer BOOLEAN NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_disclosure_answers_flag_key
            UNIQUE (draft_version_id, flag_name),
          CONSTRAINT findraft_disclosure_answers_company_fk
            FOREIGN KEY (org_id, company_id)
            REFERENCES companies (org_id, id) ON DELETE CASCADE,
          CONSTRAINT findraft_disclosure_answers_draft_fk
            FOREIGN KEY (draft_version_id, org_id, company_id)
            REFERENCES findraft_draft_versions (id, org_id, company_id)
            ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_disclosure_answers_org_id
          ON findraft_disclosure_answers (org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_disclosure_answers_draft_id
          ON findraft_disclosure_answers (draft_version_id)
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_disclosure_answers_locked_draft
        BEFORE INSERT OR UPDATE OR DELETE ON findraft_disclosure_answers
        FOR EACH ROW
        EXECUTE FUNCTION findraft_refuse_locked_draft_child();
        """
    )
    op.execute(
        """
        CREATE TABLE findraft_draft_operations (
          id UUID PRIMARY KEY,
          org_id UUID NOT NULL REFERENCES organisations (id) ON DELETE CASCADE,
          company_id UUID NOT NULL,
          draft_version_id UUID NOT NULL,
          action VARCHAR(32) NOT NULL,
          idempotency_key VARCHAR(200) NOT NULL,
          request_sha256 VARCHAR(64) NOT NULL,
          response JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT findraft_draft_operations_idempotency_key
            UNIQUE (org_id, idempotency_key),
          CONSTRAINT findraft_draft_operations_draft_fk
            FOREIGN KEY (draft_version_id, org_id, company_id)
            REFERENCES findraft_draft_versions (id, org_id, company_id)
            ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_draft_operations_org_id
          ON findraft_draft_operations (org_id)
        """
    )
    for table in (
        "findraft_adjustment_journals",
        "findraft_adjustment_lines",
        "findraft_disclosure_answers",
        "findraft_draft_operations",
    ):
        _rls(table)
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'findraft_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON findraft_adjustment_journals TO findraft_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON findraft_adjustment_lines TO findraft_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON findraft_disclosure_answers TO findraft_app;
            GRANT SELECT, INSERT ON findraft_draft_operations TO findraft_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS findraft_draft_operations")
    op.execute("DROP TABLE IF EXISTS findraft_disclosure_answers")
    op.execute("DROP TABLE IF EXISTS findraft_adjustment_lines")
    op.execute("DROP TABLE IF EXISTS findraft_adjustment_journals")
    op.execute(
        "DROP FUNCTION IF EXISTS findraft_adjustment_journal_must_balance()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_confirmed_mappings_locked_draft "
        "ON findraft_confirmed_mappings"
    )
    op.execute("DROP FUNCTION IF EXISTS findraft_refuse_mapping_on_locked_draft()")
    op.execute("DROP FUNCTION IF EXISTS findraft_refuse_locked_draft_child()")
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_draft_status_guard "
        "ON findraft_draft_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS findraft_draft_status_guard()")
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          DROP CONSTRAINT IF EXISTS findraft_draft_versions_final_snapshot_check,
          DROP CONSTRAINT IF EXISTS findraft_draft_versions_id_org_company_key,
          DROP COLUMN IF EXISTS finalised_by_user_id,
          DROP COLUMN IF EXISTS engine_sha,
          DROP COLUMN IF EXISTS inputs_sha256,
          DROP COLUMN IF EXISTS snapshot,
          DROP COLUMN IF EXISTS row_version
        """
    )
