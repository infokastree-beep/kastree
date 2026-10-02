"""Year end may adopt one completed Product 1 trial balance.

Revision ID: y5z6a7b8c9
Revises: x4y5z6a7b8
Create Date: 2026-10-02

The column is a pointer. Adopting does not insert findraft_tb_versions,
findraft_tb_lines, or findraft_confirmed_mappings. A trigger refuses a
trial balance that belongs to another company. Deleting the trial balance
clears the pointer and leaves the year end in place.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "y5z6a7b8c9"
down_revision: Union[str, None] = "x4y5z6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE findraft_year_ends
          ADD COLUMN adopted_trial_balance_id UUID,
          ADD CONSTRAINT findraft_year_ends_adopted_tb_fk
            FOREIGN KEY (adopted_trial_balance_id)
            REFERENCES trial_balances (id)
            ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE INDEX idx_findraft_year_ends_adopted_tb
          ON findraft_year_ends (adopted_trial_balance_id)
          WHERE adopted_trial_balance_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION findraft_year_ends_adopted_tb_company()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE
          tb_company uuid;
          tb_deleted boolean;
        BEGIN
          IF NEW.adopted_trial_balance_id IS NULL THEN
            RETURN NEW;
          END IF;
          SELECT company_id, is_deleted
            INTO tb_company, tb_deleted
          FROM trial_balances
          WHERE id = NEW.adopted_trial_balance_id;
          IF tb_company IS NULL OR tb_deleted THEN
            RAISE EXCEPTION
              'adopted trial balance is not an active trial balance';
          END IF;
          IF tb_company IS DISTINCT FROM NEW.company_id THEN
            RAISE EXCEPTION
              'adopted trial balance belongs to another company';
          END IF;
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER findraft_year_ends_adopted_tb_company
        BEFORE INSERT OR UPDATE OF adopted_trial_balance_id
        ON findraft_year_ends
        FOR EACH ROW
        EXECUTE FUNCTION findraft_year_ends_adopted_tb_company();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS findraft_year_ends_adopted_tb_company "
        "ON findraft_year_ends"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS findraft_year_ends_adopted_tb_company()"
    )
    op.execute("DROP INDEX IF EXISTS idx_findraft_year_ends_adopted_tb")
    op.execute(
        "ALTER TABLE findraft_year_ends "
        "DROP CONSTRAINT IF EXISTS findraft_year_ends_adopted_tb_fk"
    )
    op.execute(
        "ALTER TABLE findraft_year_ends "
        "DROP COLUMN IF EXISTS adopted_trial_balance_id"
    )
