"""Page numbers, the notes line, and the balance-sheet signature."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.services.statutory_statements import (
    build_statutory_statements,
    write_statement_pdf,
)
from tests.test_reconciliation import _FA_REGISTER, _MAPPINGS, _TB, _lines
from tests.test_statutory_statements import _entity, _golden

_ARTIFACTS = Path("/opt/cursor/artifacts")
_NOTES_LINE = "The notes form part of these financial statements"


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
        entity=_entity(),
        approval_date="15 March 2027",
        signing_directors="Ada Lovelace",
    )


def test_furniture_and_the_balance_sheet_signature() -> None:
    golden = _golden()
    signed = build_statutory_statements(
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
        approval_date="15 March 2027",
        signing_directors="Ada Lovelace, Grace Hopper",
    )
    first = _first_period()
    assert golden.net_assets == Decimal("455812.00")
    assert golden.profit == Decimal("157650.00")
    assert signed.net_assets == golden.net_assets
    assert signed.profit == golden.profit
    assert first.net_assets == Decimal("35000.00")
    assert first.profit == Decimal("25000.00")
    assert golden.html is not None
    assert signed.html is not None
    assert first.html is not None
    for html in (golden.html, signed.html, first.html):
        assert "counter(page)" in html
        assert _NOTES_LINE in html
        assert "break-after: avoid" in html
        assert "Approved by the board and signed on its behalf by" in html
    assert "A signatory has not been recorded." in golden.html
    assert "Approval date has not been recorded." in golden.html
    sofp = signed.html.split('<section data-section="sofp">', 1)[1]
    assert "Ada Lovelace" in sofp
    assert "Grace Hopper" in sofp
    assert "Approved on 15 March 2027." in sofp
    assert "Ada Lovelace" in first.html
    assert "Approved on 15 March 2027." in first.html
    iso = build_statutory_statements(
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
        approval_date="2027-03-17",
        signing_directors="Ada Lovelace",
    )
    assert iso.net_assets == golden.net_assets
    assert iso.profit == golden.profit
    assert iso.html is not None
    iso_signature = iso.html.split('class="signature"', 1)[1]
    assert "Approved on 17 March 2027." in iso_signature
    assert "2027-03-17" not in iso_signature
    golden_pdf = write_statement_pdf(golden.html)
    first_pdf = write_statement_pdf(first.html)
    assert golden_pdf.startswith(b"%PDF")
    assert first_pdf.startswith(b"%PDF")
    if _ARTIFACTS.is_dir():
        (_ARTIFACTS / "statutory-golden-furniture.pdf").write_bytes(golden_pdf)
        (_ARTIFACTS / "statutory-first-period-furniture.pdf").write_bytes(first_pdf)
