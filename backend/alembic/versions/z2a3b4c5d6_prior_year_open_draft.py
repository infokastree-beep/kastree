"""An open draft may replace comparatives and undo the first period.

Revision ID: z2a3b4c5d6
Revises: y1z2a3b4c5
Create Date: 2026-10-14

The year-end and prior-line triggers refused every change once
prior_year_validated was true. A final, locked, or frozen latest draft
still refuses. An open draft, or a year end with no draft, may replace
the lines and clear the first-period flags. No new column. No GRANT ALL.
"""

from pathlib import Path
from typing import Sequence, Union

from alembic import op

revision: str = "z2a3b4c5d6"
down_revision: Union[str, None] = "y1z2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRIVILEGES = (
    Path(__file__).resolve().parents[2] / "scripts" / "findraft_table_privileges.sql"
)

_OPEN_YEAR = """
CREATE OR REPLACE FUNCTION findraft_year_ends_prior_locked()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  latest_status text;
  latest_frozen boolean;
BEGIN
  IF NOT OLD.prior_year_validated THEN
    RETURN NEW;
  END IF;
  IF NEW.prior_year_validated IS NOT DISTINCT FROM OLD.prior_year_validated
     AND NEW.first_financial_period IS NOT DISTINCT FROM OLD.first_financial_period THEN
    RETURN NEW;
  END IF;
  SELECT status, is_frozen
    INTO latest_status, latest_frozen
    FROM findraft_draft_versions
   WHERE year_end_id = OLD.id
   ORDER BY version_number DESC
   LIMIT 1;
  IF latest_status IN ('final', 'locked') OR latest_frozen THEN
    RAISE EXCEPTION 'prior year is already validated';
  END IF;
  RETURN NEW;
END;
$$;
"""

_OPEN_LINES = """
CREATE OR REPLACE FUNCTION findraft_prior_year_lines_locked()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  locked boolean;
  year_end uuid;
  latest_status text;
  latest_frozen boolean;
BEGIN
  IF TG_OP = 'DELETE' THEN
    year_end := OLD.year_end_id;
  ELSE
    year_end := NEW.year_end_id;
  END IF;
  SELECT prior_year_validated INTO locked
    FROM findraft_year_ends WHERE id = year_end;
  IF NOT COALESCE(locked, false) THEN
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RETURN NEW;
  END IF;
  SELECT status, is_frozen
    INTO latest_status, latest_frozen
    FROM findraft_draft_versions
   WHERE year_end_id = year_end
   ORDER BY version_number DESC
   LIMIT 1;
  IF latest_status IN ('final', 'locked') OR latest_frozen THEN
    RAISE EXCEPTION 'prior year is already validated';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;
"""

_CLOSED_YEAR = """
CREATE OR REPLACE FUNCTION findraft_year_ends_prior_locked()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.prior_year_validated THEN
    RAISE EXCEPTION 'prior year is already validated';
  END IF;
  RETURN NEW;
END;
$$;
"""

_CLOSED_LINES = """
CREATE OR REPLACE FUNCTION findraft_prior_year_lines_locked()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  locked boolean;
  year_end uuid;
BEGIN
  year_end := COALESCE(NEW.year_end_id, OLD.year_end_id);
  SELECT prior_year_validated INTO locked
    FROM findraft_year_ends WHERE id = year_end;
  IF locked THEN
    RAISE EXCEPTION 'prior year is already validated';
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;
"""


def upgrade() -> None:
    op.execute(_OPEN_YEAR)
    op.execute(_OPEN_LINES)
    op.execute(_PRIVILEGES.read_text())


def downgrade() -> None:
    op.execute(_CLOSED_YEAR)
    op.execute(_CLOSED_LINES)
    op.execute(_PRIVILEGES.read_text())
