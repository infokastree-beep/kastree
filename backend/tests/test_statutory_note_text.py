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
    assert "[average number of employees not recorded]" in employees.body
    recorded = _golden(entity=_entity(average_employees="12"))
    recorded_employees = next(
        note for note in recorded.notes if note.code == "N8_EMPLOYEES"
    )
    assert "was 12 (" in recorded_employees.body
    assert golden.html is not None and first.html is not None
    golden_pdf = write_statement_pdf(golden.html)
    first_pdf = write_statement_pdf(first.html)
    assert golden_pdf.startswith(b"%PDF")
    assert first_pdf.startswith(b"%PDF")
    if _ARTIFACTS.is_dir():
        (_ARTIFACTS / "statutory-golden-notes.pdf").write_bytes(golden_pdf)
        (_ARTIFACTS / "statutory-first-period-notes.pdf").write_bytes(first_pdf)
