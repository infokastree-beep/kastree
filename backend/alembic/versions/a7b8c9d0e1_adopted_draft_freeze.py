"""Adopted statutory drafts: mapping fingerprint and freeze.

Revision ID: a7b8c9d0e1
Revises: z6a7b8c9d0
Create Date: 2026-10-02

A continuation draft keeps tb_version_id null. mappings_sha256 is the
acknowledged Product 1 fingerprint. Freezing a draft stores the computation
base and refuses later child writes. The status stays draft or locked.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a7b8c9d0e1"
down_revision: Union[str, None] = "z6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_draft_versions
          ADD COLUMN mappings_sha256 VARCHAR(64),
          ADD COLUMN frozen_inputs JSONB,
          ADD COLUMN is_frozen BOOLEAN NOT NULL DEFAULT false
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
          IF OLD.is_frozen AND (
            NEW.is_frozen IS DISTINCT FROM OLD.is_frozen
            OR NEW.frozen_inputs IS DISTINCT FROM OLD.frozen_inputs
            OR NEW.status IS DISTINCT FROM OLD.status
            OR NEW.mappings_sha256 IS DISTINCT FROM OLD.mappings_sha256
          ) THEN
            RAISE EXCEPTION 'frozen draft is immutable';
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
        CREATE OR REPLACE FUNCTION findraft_refuse_locked_draft_child()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          parent_status text;
          parent_frozen boolean;
          draft_id uuid;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            draft_id := OLD.draft_version_id;
          ELSE
            draft_id := NEW.draft_version_id;
          END IF;
          SELECT status, is_frozen INTO parent_status, parent_frozen
          FROM findraft_draft_versions
          WHERE id = draft_id;
          IF parent_status IN ('locked', 'final') THEN
            RAISE EXCEPTION 'draft is %; writes are refused', parent_status;
          END IF;
          IF parent_frozen THEN
            RAISE EXCEPTION 'draft is frozen; writes are refused';
          END IF;
          IF TG_OP = 'DELETE' THEN
            RETURN OLD;
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )


def downgrade() -> None:
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
        ALTER TABLE findraft_draft_versions
          DROP COLUMN mappings_sha256,
          DROP COLUMN frozen_inputs,
          DROP COLUMN is_frozen
        """
    )
