"""A frozen adopted draft may be finalised once.

Revision ID: j6k7l8m9n0
Revises: i5j6k7l8m9
Create Date: 2026-10-10

``start_new_report`` freezes the previous draft and leaves its status as
draft. Finalise has to set that status to final and write the snapshot.
``findraft_draft_status_guard`` from a7b8c9d0e1 refused every status change
on a frozen row (``frozen draft is immutable``), so the approved finalise
could not commit.

This revision replaces that function. A frozen row may move to status
final. ``is_frozen``, ``frozen_inputs``, and ``mappings_sha256`` stay
unchanged, and any other status change is still refused. The FINAL
immutability check above it is unchanged. No table or column is added.
Downgrade restores the previous function body. No GRANT ALL.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "j6k7l8m9n0"
down_revision: Union[str, None] = "i5j6k7l8m9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
            OR NEW.mappings_sha256 IS DISTINCT FROM OLD.mappings_sha256
            OR (
              NEW.status IS DISTINCT FROM OLD.status
              AND NEW.status IS DISTINCT FROM 'final'
            )
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
