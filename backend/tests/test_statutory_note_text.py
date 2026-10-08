"""Note sentences name only statements and notes that this render includes."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from app.services.statutory_display import format_whole
from app.services.statutory_statements import (
    _CREDITORS_CROSS_REF,
    _retarget_cross_references,
    build_statutory_statements,
    write_statement_pdf,
)
from tests.test_reconciliation import _lines
from tests.test_statutory_statements import _entity, _golden

_ARTIFACTS = Path("/opt/cursor/artifacts")
_NOTE_REF = re.compile(r"\bNotes?\s+(\d+)\b")
_RENDERED_STATEMENTS = (
    "statement of financial position",
    "income statement",
)
_NAMED_STATEMENTS = _RENDERED_STATEMENTS + (
    "balance sheet",
    "statement of comprehensive income",
    "statement of changes in equity",
    "statement of changes in retained earnings",
    "statement of cash flows",
    "cash flow statement",
    "socie",
)
_INTERNAL_CODES = (
    "N0_ENTITY",
    "N1_POLICIES",
    "N2_FA",
    "N3_DEBTORS",
    "N4_CREDITORS",
    "N5_LOANS",
    "N6_CAPITAL",
    "N7_RPT",
    "N8_EMPLOYEES",
    "N9_COMMITMENTS",
    "TRADE_DEBTORS",
    "OTHER_DEBTORS",
    "TRADE_CREDITORS",
)


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
    )


def _sentences(body: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", body) if part.strip()]


_COMMITMENT_FLAGS = (
    "COMMITMENTS_EXIST",
    "GUARANTEES_EXIST",
    "SUBSEQUENT_EVENTS",
    "PENSION_COMMITMENT",
    "CHARGES_EXIST",
    "OFF_BALANCE_ARRANGEMENT",
)


def test_unanswered_related_party_and_commitment_notes_are_one_line() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    related = next(note for note in document.notes if note.code == "N7_RPT")
    commitments = next(note for note in document.notes if note.code == "N9_COMMITMENTS")
    assert related.body == "[related party transactions not recorded]"
    assert commitments.body == "[commitments and contingencies not recorded]"
    assert "Companies Act 2014" not in related.body
    declined = _golden(
        disclosure_flags={
            "RPT_EXISTS": False,
            "DIRECTORS_EXIST": False,
            **{name: False for name in _COMMITMENT_FLAGS},
        }
    )
    assert declined.net_assets == document.net_assets
    assert declined.profit == document.profit
    assert "N7_RPT" not in {note.code for note in declined.notes}
    assert "N9_COMMITMENTS" not in {note.code for note in declined.notes}
    numbers = [int(note.title.split(".", 1)[0]) for note in declined.notes if note.title]
    assert numbers == list(range(1, len(numbers) + 1))
    affirmed = _golden(
        disclosure_flags={
            "RPT_EXISTS": True,
            "COMMITMENTS_EXIST": True,
        }
    )
    assert affirmed.net_assets == document.net_assets
    assert affirmed.profit == document.profit
    related_yes = next(note for note in affirmed.notes if note.code == "N7_RPT")
    commitments_yes = next(note for note in affirmed.notes if note.code == "N9_COMMITMENTS")
    assert "Companies Act 2014" in related_yes.body
    assert "[related party transactions not recorded]" in related_yes.body
    assert "[directors' aggregate disclosures not recorded]" in related_yes.body
    for placeholder in (
        "[capital commitments not recorded]",
        "[retirement benefit commitments not recorded]",
        "[guarantees and security not recorded]",
        "[charges on assets not recorded]",
        "[subsequent events not recorded]",
    ):
        assert placeholder in commitments_yes.body
    assert commitments_yes.body != "[commitments and contingencies not recorded]"


def test_a_missing_creditors_note_is_not_cited() -> None:
    source = (
        "Details of loans outstanding at the reporting date are set out below. "
        + _CREDITORS_CROSS_REF
    )
    dropped = _retarget_cross_references(source, {})
    assert "Note" not in dropped
    retargeted = _retarget_cross_references(source, {"N4_CREDITORS": 5})
    assert "Note 5." in retargeted
    assert "Note 4" not in retargeted


def test_note_sentences_name_only_rendered_statements_and_notes() -> None:
    golden = _golden()
    first = _first_period()
    assert golden.net_assets == Decimal("455812.00")
    assert golden.profit == Decimal("157650.00")
    assert first.net_assets == Decimal("35000.00")
    assert first.profit == Decimal("25000.00")
    for document in (golden, first):
        assert document.html is not None
        numbers: list[int] = []
        for note in document.notes:
            assert note.title is not None
            head, _, human = note.title.partition(". ")
            assert head.isdigit()
            assert human
            assert note.code not in note.title
            numbers.append(int(head))
        assert numbers == list(range(1, len(numbers) + 1))
        for note in document.notes:
            for sentence in _sentences(note.body):
                lowered = sentence.lower()
                for name in _NAMED_STATEMENTS:
                    if name in lowered:
                        assert name in _RENDERED_STATEMENTS, sentence
                for match in _NOTE_REF.finditer(sentence):
                    assert int(match.group(1)) in numbers, sentence
        html = document.html
        for code in _INTERNAL_CODES:
            assert code not in html
        assert "<th>Notes</th>" in html
    loans = next(note for note in golden.notes if note.code == "N5_LOANS")
    assert "Note 5." in loans.body
    assert "Note 4" not in loans.body
    capital = next(note for note in golden.notes if note.code == "N6_CAPITAL")
    share = next(row for row in golden.sofp if row.label == "Called up share capital")
    assert f"is {format_whole(share.current)}" in capital.body
    assert "[share class analysis not recorded]" in capital.body
    assert "statement of changes" not in capital.body.lower()
    assert "<td>Trade debtors</td><td>4</td>" in golden.html
    assert "<td>Trade debtors</td><td>3</td>" in first.html
    assert "N2_FA" not in {note.code for note in first.notes}
    assert "<td>Tangible assets</td>" not in first.html
    assert "<td>Cash at bank and in hand</td><td></td>" in first.html
    blank = _golden(
        entity=_entity(
            registered_office="",
            company_number="",
            directors_list="",
            average_employees="",
        )
    )
    entity_note = next(note for note in blank.notes if note.code == "N0_ENTITY")
    employees = next(note for note in blank.notes if note.code == "N8_EMPLOYEES")
    assert "[registered office not recorded]" in entity_note.body
    assert "[company number not recorded]" in entity_note.body
    assert "[directors not recorded]" in entity_note.body
    assert entity_note.body.count("[") >= 3
    assert employees.body.count("[average number of employees not recorded]") == 1
    assert "(" not in employees.body
    recorded = _golden(entity=_entity(average_employees="12"))
    recorded_employees = next(
        note for note in recorded.notes if note.code == "N8_EMPLOYEES"
    )
    assert recorded_employees.body.endswith(
        "was 12 ([average number of employees not recorded])."
    )
    first_blank = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(
            (
                ("1000", "Cash at Bank", 30000, 0),
                ("1100", "Trade Debtors", 20000, 0),
                ("2000", "Trade Creditors", 0, 15000),
                ("3000", "Share Capital", 0, 10000),
                ("4000", "Sales Revenue", 0, 100000),
                ("5000", "Cost of Sales", 40250, 0),
                ("6000", "Operating Expenses", 34750, 0),
            )
        ),
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
        entity=_entity(average_employees=""),
        period_start="2026-01-01",
        period_end="2026-12-31",
        first_financial_period=True,
    )
    first_employees = next(
        note for note in first_blank.notes if note.code == "N8_EMPLOYEES"
    )
    assert first_employees.body.count("[average number of employees not recorded]") == 1
    assert "(" not in first_employees.body
    first_counted = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(
            (
                ("1000", "Cash at Bank", 30000, 0),
                ("1100", "Trade Debtors", 20000, 0),
                ("2000", "Trade Creditors", 0, 15000),
                ("3000", "Share Capital", 0, 10000),
                ("4000", "Sales Revenue", 0, 100000),
                ("5000", "Cost of Sales", 40250, 0),
                ("6000", "Operating Expenses", 34750, 0),
            )
        ),
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
        entity=_entity(average_employees="12"),
        period_start="2026-01-01",
        period_end="2026-12-31",
        first_financial_period=True,
    )
    counted = next(note for note in first_counted.notes if note.code == "N8_EMPLOYEES")
    assert counted.body.endswith("was 12.")
    assert "(" not in counted.body
    assert golden.html is not None and first.html is not None
    for html in (golden.html, first.html):
        assert "<caption>" not in html
        tables = re.findall(r"<table>.*?</table>", html, flags=re.DOTALL)
        assert tables
        for table in tables:
            assert "for the year ended" not in table
            assert "for the period from" not in table
    golden_pdf = write_statement_pdf(golden.html)
    first_pdf = write_statement_pdf(first.html)
    assert golden_pdf.startswith(b"%PDF")
    assert first_pdf.startswith(b"%PDF")
    if _ARTIFACTS.is_dir():
        (_ARTIFACTS / "statutory-golden-notes.pdf").write_bytes(golden_pdf)
        (_ARTIFACTS / "statutory-first-period-notes.pdf").write_bytes(first_pdf)
