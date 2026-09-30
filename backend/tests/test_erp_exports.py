"""Real-world ERP/accounting-system TB export format library.

Each fixture under tests/fixtures/erp_exports/ is a genuinely different export
shape (Xero/Sage/QuickBooks/manual, plus header-wording/ordering/zero/sign
variants). Add new real formats here so column-detection robustness cannot
silently regress.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.services.parser import TOLERANCE, parse_tb_file

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "erp_exports"


def _parse(name: str):
    return parse_tb_file((FIXTURES / name).read_bytes(), filename=name)


@pytest.mark.parametrize(
    "name,expected_total",
    [
        ("xero_trial_balance.csv", Decimal("66300.00")),          # single "Account" column
        ("sage_trial_balance.csv", Decimal("182000.00")),         # nil/- zeros, Nominal Code
        ("quickbooks_trial_balance.csv", Decimal("80000.00")),    # single "Account" column
        ("dr_cr_abbrev_tb.csv", Decimal("10000.00")),             # Dr/Cr headers
        ("signed_balance_dr_cr_tb.csv", Decimal("10000.00")),     # "x DR"/"x CR" balance
        ("reordered_name_first_tb.csv", Decimal("10000.00")),     # Name before Code
        ("zero_representations_tb.csv", Decimal("10000.00")),     # -, nil, blank, 0.00
        ("manual_spreadsheet_tb.xlsx", Decimal("20000.00")),      # title rows above header
    ],
)
def test_erp_export_parses_balanced(name: str, expected_total: Decimal) -> None:
    rows = _parse(name)
    assert rows, f"{name} produced no rows"
    total_debits = sum((r.debit for r in rows), Decimal("0"))
    total_credits = sum((r.credit for r in rows), Decimal("0"))
    assert abs(total_debits - total_credits) <= TOLERANCE, (
        f"{name} unbalanced: dr={total_debits} cr={total_credits}"
    )
    assert total_debits == expected_total, f"{name} dr={total_debits} != {expected_total}"


def test_signed_balance_dr_cr_assigns_sign_correctly() -> None:
    rows = {r.account_name: r for r in _parse("signed_balance_dr_cr_tb.csv")}
    assert rows["Cash at bank"].debit == Decimal("10000.00")   # DR -> debit
    assert rows["Share capital"].credit == Decimal("10000.00")  # CR -> credit


def test_xero_single_account_column_detected() -> None:
    rows = _parse("xero_trial_balance.csv")
    # Single "Account" column becomes the account identifier; still parses balanced.
    assert any("Sales" in r.account_name for r in rows)
    assert len(rows) == 5
