"""Statutory PDF display. Engine decimals stay exact."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from app.services.statutory_display import (
    column_headings,
    face_display_rows,
    format_whole,
    format_whole_prose,
    is_twelve_months,
    statement_period_phrase,
)
from app.services.statutory_statements import (
    StatementRow,
    build_statutory_statements,
    write_statement_pdf,
)
from findraft.engine.rounding import rounding_gap
from findraft.engine.statements import SOFP_COMPLIANCE_STATEMENT
from tests.test_reconciliation import _FA_REGISTER, _MAPPINGS, _TB, _lines
from tests.test_statutory_statements import _entity, _golden, _row

_ARTIFACTS = Path("/opt/cursor/artifacts")


def test_whole_units_use_commas_and_brackets() -> None:
    assert format_whole(Decimal("-40250.00")) == "(40,250)"
    assert format_whole(Decimal("25000")) == "25,000"
    assert format_whole(Decimal("0")) == "0"
    assert format_whole_prose(Decimal("157650"), "EUR") == "€157,650"
    assert format_whole_prose(Decimal("-10"), "GBP") == "(£10)"


def test_twelve_months_and_a_shorter_period_use_different_phrases() -> None:
    assert is_twelve_months(date(2026, 1, 1), date(2026, 12, 31)) is True
    assert is_twelve_months(date(2024, 2, 29), date(2025, 2, 28)) is True
    short = statement_period_phrase(date(2026, 3, 1), date(2026, 12, 31))
    assert short == "for the period from 1 March 2026 to 31 December 2026"
    year = statement_period_phrase(date(2026, 1, 1), date(2026, 12, 31))
    assert year == "for the year ended 31 December 2026"
    assert statement_period_phrase(None, date(2026, 12, 31)) == year


def test_rounding_difference_matches_the_engine_helper() -> None:
    rows = (
        StatementRow("Stocks", Decimal("1.40"), Decimal("0")),
        StatementRow("Trade debtors", Decimal("1.40"), Decimal("0")),
        StatementRow("Other debtors", Decimal("0"), Decimal("0")),
        StatementRow("Cash at bank and in hand", Decimal("0"), Decimal("0")),
        StatementRow("Total current assets", Decimal("2.80"), Decimal("0")),
    )
    children = [row.current for row in rows[:-1]]
    gap = rounding_gap(children, rows[-1].current, Decimal("1"))
    printed = face_display_rows(rows, comparative=True)
    labels = [str(row["label"]) for row in printed]
    assert "Other debtors" not in labels
    assert "Cash at bank and in hand" not in labels
    difference = next(row for row in printed if row["label"] == "Rounding difference")
    assert difference["amounts"][0] == format_whole(-gap)
    assert gap == Decimal("-1")


def test_nil_lines_leave_the_pdf_and_stay_on_the_engine_rows() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert _row(document.sofp, "Intangible assets").current == Decimal("0.00")
    assert _row(document.sofp, "Net assets").current == document.net_assets
    assert document.html is not None
    assert "<td>Intangible assets</td>" not in document.html
    assert "<td>Net assets</td>" in document.html


def test_first_period_omits_the_comparative_and_a_short_period_keeps_it() -> None:
    first = _first_period()
    assert first.profit == Decimal("25000.00")
    assert first.net_assets == Decimal("35000.00")
    assert first.html is not None
    assert "for the year ended 31 December 2026" in first.html
    assert "as at 31 December 2026" in first.html
    assert "2025 €" not in first.html
    assert "2026 €" in first.html
    assert "<td>Tangible assets</td>" not in first.html
    assert "(40,250)" in first.html
    assert _row(first.sofp, "Tangible assets").current == Decimal("0.00")
    short = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={
            "FA_PLANT_COST": Decimal("111400.00"),
            "RETAINED_EARNINGS": Decimal("-322062.00"),
        },
        fa_register=_FA_REGISTER,
        entity=_entity(),
        period_start="2026-03-01",
        period_end="2026-12-31",
        first_financial_period=False,
    )
    assert short.net_assets == Decimal("455812.00")
    assert short.html is not None
    assert "for the period from 1 March 2026 to 31 December 2026" in short.html
    assert "2025 €" in short.html
    assert short.compliance_statement == SOFP_COMPLIANCE_STATEMENT


def test_a_non_euro_currency_does_not_change_the_irish_pack_wording() -> None:
    document = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={
            "FA_PLANT_COST": Decimal("111400.00"),
            "RETAINED_EARNINGS": Decimal("-322062.00"),
        },
        fa_register=_FA_REGISTER,
        entity=_entity(currency="GBP"),
        period_start="2026-01-01",
        period_end="2026-12-31",
    )
    assert document.profit == Decimal("157650.00")
    assert document.compliance_statement == SOFP_COMPLIANCE_STATEMENT
    assert document.html is not None
    assert "2026 £" in document.html
    policies = next(note for note in document.notes if note.code == "N1_POLICIES")
    assert "pound sterling" in policies.body
    assert "FRS 102" in policies.body
    assert "Companies Act 2014" in policies.body
    assert column_headings(
        period_end=date(2026, 12, 31), currency_code="CHF", comparative=True
    ) == ["2026 CHF", "2025 CHF"]


def test_acceptance_pdfs_keep_the_engine_figures() -> None:
    golden = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={
            "FA_PLANT_COST": Decimal("111400.00"),
            "RETAINED_EARNINGS": Decimal("-322062.00"),
        },
        fa_register=_FA_REGISTER,
        entity=_entity(),
        period_start="2025-01-01",
        period_end="2025-12-31",
    )
    first = _first_period()
    assert golden.net_assets == Decimal("455812.00")
    assert golden.profit == Decimal("157650.00")
    assert first.net_assets == Decimal("35000.00")
    assert first.profit == Decimal("25000.00")
    assert golden.html is not None and first.html is not None
    golden_pdf = write_statement_pdf(golden.html)
    first_pdf = write_statement_pdf(first.html)
    assert golden_pdf.startswith(b"%PDF")
    assert first_pdf.startswith(b"%PDF")
    if _ARTIFACTS.is_dir():
        (_ARTIFACTS / "statutory-golden-format.pdf").write_bytes(golden_pdf)
        (_ARTIFACTS / "statutory-first-period-format.pdf").write_bytes(first_pdf)


def _first_period():
    rows = (
        ("1000", "Cash at Bank", 30000, 0),
        ("1100", "Trade Debtors", 20000, 0),
        ("2000", "Trade Creditors", 0, 15000),
        ("3000", "Share Capital", 0, 10000),
        ("4000", "Sales Revenue", 0, 100000),
        ("5000", "Cost of Sales", 40250, 0),
        ("6000", "Operating Expenses", 34750, 0),
    )
    return build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(rows),
        mappings={
            "1000": "CASH",
            "1100": "TRADE_DEBTORS",
            "2000": "TRADE_CREDITORS",
            "3000": "SHARE_CAPITAL",
            "4000": "REVENUE",
            "5000": "COST_OF_SALES",
            "6000": "ADMIN_EXPENSES",
        },
        prior_retained_earnings=Decimal("0"),
        prior_canonical={},
        entity=_entity(currency="EUR"),
        period_start="2026-01-01",
        period_end="2026-12-31",
        first_financial_period=True,
    )
