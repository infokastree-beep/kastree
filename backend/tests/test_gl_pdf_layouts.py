"""Real-world GL/TB PDF layout regression library.

Every fixture here is a committed PDF under tests/fixtures/gl_pdf/. New real-world
layouts should be ADDED here so nothing tested regresses silently.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.gl_to_tb import convert_gl_file_to_tb, convert_gl_to_tb, parse_gl_pdf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "gl_pdf"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_apex_real_file_converts_to_stated_control_total() -> None:
    """The exact real file that exposed the banner-layout bug.

    Acceptance: its own stated control total, Balanced ($18,485,200.00). This
    document is a TB summary + partial GL detail; uploaded via the GL path it must
    still yield the real, balanced trial balance.
    """
    result = convert_gl_file_to_tb(
        _read("apex_global_tb_and_gl.pdf"),
        "Apex_Global_Technologies.pdf",
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        mode="C",
    )
    assert result.total_debits == result.total_credits == Decimal("18485200.00")
    assert len(result.rows) == 16
    by_code = {r.account_code: r for r in result.rows}
    assert by_code["1010"].debit == Decimal("2450800.00")
    assert by_code["4010"].credit == Decimal("7000000.00")


def test_banner_grouped_gl_parses_via_scanned_header_and_banner_code() -> None:
    """Grouped/banner ledger: header is not row 0, and rows have no per-row code.

    Confirms header-row scanning + account-banner code propagation + Ending Balance
    skipping all work together and produce a balanced TB.
    """
    pdf = _read("banner_grouped_gl_balanced.pdf")
    lines = parse_gl_pdf(pdf)
    # Every transaction row inherited its account code from the banner above it.
    assert {ln.account_code for ln in lines} == {"1000", "4000", "5000"}
    assert all(ln.txn_date is not None for ln in lines)  # wrapped/plain dates parsed

    result = convert_gl_to_tb(
        lines, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30), mode="C"
    )
    # Net presentation: Bank +900 (1200-300), Sales -1200, Cost +300 -> balanced 1200.
    assert result.total_debits == result.total_credits == Decimal("1200.00")
    assert {r.account_code for r in result.rows} == {"1000", "4000", "5000"}
