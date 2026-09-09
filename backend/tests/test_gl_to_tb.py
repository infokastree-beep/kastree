"""Phase 3 GL → TB conversion — unit tests (modes A/B/C, balance gate)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.gl_to_tb import (
    GlImbalanceError,
    GlLine,
    ModeBRequiresPriorError,
    PriorTbSeed,
    convert_gl_file_to_tb,
    convert_gl_to_tb,
    rows_to_csv_bytes,
)
from app.services.parser import parse_tb_file


def _balanced_ytd_csv() -> bytes:
    """Genuine clean YTD GL — balanced closing TB under Mode C."""
    return (
        "Date,Account Code,Account Name,Debit,Credit\n"
        "2025-01-05,1000,Bank,10000.00,0\n"
        "2025-01-05,3000,Share Capital,0,10000.00\n"
        "2025-03-15,1100,Trade Receivables,2500.00,0\n"
        "2025-03-15,4000,Sales,0,2500.00\n"
        "2025-06-01,5000,Cost of Sales,900.00,0\n"
        "2025-06-01,1000,Bank,0,900.00\n"
        "2025-08-20,6000,Rent,1200.00,0\n"
        "2025-08-20,1000,Bank,0,1200.00\n"
        # Outside window — must be excluded
        "2026-01-10,1000,Bank,50.00,0\n"
        "2026-01-10,4000,Sales,0,50.00\n"
    ).encode("utf-8")


def _unbalanced_gl_csv() -> bytes:
    """Deliberately broken — debit posted without balancing credit."""
    return (
        "Date,Account Code,Account Name,Debit,Credit\n"
        "2025-01-05,1000,Bank,10000.00,0\n"
        "2025-01-05,3000,Share Capital,0,10000.00\n"
        "2025-03-15,1100,Trade Receivables,2500.00,0\n"
        # Missing credit leg for sales — imbalance of 2500
    ).encode("utf-8")


def test_mode_c_clean_gl_produces_balanced_tb() -> None:
    result = convert_gl_file_to_tb(
        _balanced_ytd_csv(),
        "clean-gl.csv",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        mode="C",
    )
    assert result.pipeline_eligible is True
    assert result.excluded_count == 2  # Jan 2026 pair
    assert result.included_count == 8
    assert result.total_debits == result.total_credits
    # Net presentation (per-account nets), not gross movement totals
    assert result.total_debits == Decimal("12500.00")

    by_code = {r.account_code: r for r in result.rows}
    assert by_code["1000"].account_name == "Bank"
    # Bank: 10000 - 900 - 1200 = 7900 debit
    assert by_code["1000"].debit == Decimal("7900.00")
    assert by_code["1000"].credit == Decimal("0")
    assert by_code["3000"].credit == Decimal("10000.00")
    assert by_code["4000"].credit == Decimal("2500.00")
    assert by_code["5000"].debit == Decimal("900.00")
    assert by_code["6000"].debit == Decimal("1200.00")
    assert by_code["1100"].debit == Decimal("2500.00")

    # Handoff into existing parser
    csv_bytes = rows_to_csv_bytes(result.rows)
    parsed = parse_tb_file(csv_bytes, filename="from-gl.csv")
    assert len(parsed) == len(result.rows)


def test_unbalanced_gl_hard_fails_before_pipeline() -> None:
    with pytest.raises(GlImbalanceError) as exc_info:
        convert_gl_file_to_tb(
            _unbalanced_gl_csv(),
            "broken-gl.csv",
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            mode="C",
        )
    err = exc_info.value
    assert err.difference == Decimal("2500.00")
    assert err.mode == "C"
    assert err.total_debits != err.total_credits


def test_mode_b_without_prior_blocked() -> None:
    with pytest.raises(ModeBRequiresPriorError):
        convert_gl_file_to_tb(
            _balanced_ytd_csv(),
            "clean-gl.csv",
            period_start=date(2025, 6, 1),
            period_end=date(2025, 6, 30),
            mode="B",
            prior_tb=None,
        )


def test_mode_a_opening_plus_movements() -> None:
    lines = [
        GlLine(
            account_code="1000",
            account_name="Opening Balance",
            debit=Decimal("5000"),
            credit=Decimal("0"),
            row_index=1,
            txn_date=None,
            is_opening=True,
        ),
        GlLine(
            account_code="3000",
            account_name="Opening Balance",
            debit=Decimal("0"),
            credit=Decimal("5000"),
            row_index=2,
            txn_date=None,
            is_opening=True,
        ),
        GlLine(
            account_code="1000",
            account_name="Bank",
            debit=Decimal("0"),
            credit=Decimal("200"),
            row_index=3,
            txn_date=date(2025, 2, 1),
        ),
        GlLine(
            account_code="6000",
            account_name="Rent",
            debit=Decimal("200"),
            credit=Decimal("0"),
            row_index=4,
            txn_date=date(2025, 2, 1),
        ),
    ]
    result = convert_gl_to_tb(
        lines,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        mode="A",
    )
    by_code = {r.account_code: r for r in result.rows}
    assert by_code["1000"].debit == Decimal("4800")
    assert by_code["3000"].credit == Decimal("5000")
    assert by_code["6000"].debit == Decimal("200")
    assert result.opening_count == 2


def test_mode_b_with_prior_seeds() -> None:
    movements = [
        GlLine(
            account_code="1000",
            account_name="Bank",
            debit=Decimal("0"),
            credit=Decimal("100"),
            row_index=1,
            txn_date=date(2025, 2, 10),
        ),
        GlLine(
            account_code="6000",
            account_name="Rent",
            debit=Decimal("100"),
            credit=Decimal("0"),
            row_index=2,
            txn_date=date(2025, 2, 10),
        ),
    ]
    prior = [
        PriorTbSeed("1000", "Bank", Decimal("1000"), Decimal("0")),
        PriorTbSeed("3000", "Capital", Decimal("0"), Decimal("1000")),
    ]
    result = convert_gl_to_tb(
        movements,
        period_start=date(2025, 2, 1),
        period_end=date(2025, 2, 28),
        mode="B",
        prior_tb=prior,
    )
    by_code = {r.account_code: r for r in result.rows}
    assert by_code["1000"].debit == Decimal("900")
    assert by_code["3000"].credit == Decimal("1000")
    assert by_code["6000"].debit == Decimal("100")
