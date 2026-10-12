"""Printed-note polish: checklist ids, cover banner, keep-together, dividends."""

from __future__ import annotations

import re
import zipfile
from dataclasses import replace
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from app.services.beta import WORDING_BANNER
from app.services.statutory_compose import compose_pdf_parts, docx_presentation
from app.services.statutory_docx import build_docx
from app.services.statutory_pages import build_statutory_pages
from app.services.statutory_statements import render_statutory_html, write_statement_pdf
from tests.test_statutory_compose import _setup
from tests.test_statutory_display import _pdf_pages
from tests.test_statutory_statements import _golden

_CHECKLIST = re.compile(r"1AD\.\d+")


def _charge_document():
    return _golden(
        disclosure_flags={
            "COMMITMENTS_EXIST": False,
            "GUARANTEES_EXIST": False,
            "SUBSEQUENT_EVENTS": False,
            "PENSION_COMMITMENT": False,
            "CHARGES_EXIST": True,
            "OFF_BALANCE_ARRANGEMENT": False,
        }
    )


def _report(dividends: Decimal | None) -> str:
    pages = build_statutory_pages(
        company_name="Harbour Limited",
        practice_name="Harbour Practice",
        period_end="2026-12-31",
        directors="Ada Lovelace",
        secretary="",
        principal_activity="",
        currency="EUR",
        profit=Decimal("10.00"),
        size_eligible=None,
        dividends=dividends,
    )
    report = next(page for page in pages if page.heading == "Directors' report")
    return "\n".join(report.paragraphs)


def _pdf_text(html: str) -> str:
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    assert pages
    return "\n".join(pages)


def _docx_parts(payload: dict[str, object], dest: Path) -> tuple[str, list[str]]:
    build_docx(payload, dest)
    content = dest.read_bytes()
    with zipfile.ZipFile(BytesIO(content)) as archive:
        xml = archive.read("word/document.xml").decode()
        headers = [
            archive.read(name).decode()
            for name in archive.namelist()
            if name.startswith("word/header")
        ]
    return xml, headers


def test_printed_notes_use_plain_headings_in_pdf_and_word(tmp_path: Path) -> None:
    document = _charge_document()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    charges = next(note for note in document.notes if note.code == "N9_COMMITMENTS")
    assert charges.body
    assert "Charges on assets" in charges.body
    assert "[charges on assets not recorded]" in charges.body
    assert _CHECKLIST.search(charges.body) is None
    employees = next(note for note in document.notes if note.code == "N8_EMPLOYEES")
    assert employees.title is not None
    assert re.fullmatch(r"\d+\. Employees", employees.title)
    assert "1AD" not in employees.title
    assert employees.body is not None and "1AD" not in employees.body
    html, sections = compose_pdf_parts(
        document,
        report_setup=_setup(),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        currency="EUR",
    )
    assert "policy-paragraph" in html
    assert "short-note" in html
    assert ".note-paragraph" in html
    assert "break-inside: avoid" in html
    assert _CHECKLIST.search(html) is None
    printed = _pdf_text(html)
    assert "Charges on assets" in printed
    assert "1AD.28" not in printed
    assert _CHECKLIST.search(printed) is None
    assert "455,812" in printed
    assert "157,650" in printed
    assert "A dividend has been recorded for the financial year." in printed
    xml, _headers = _docx_parts(
        {
            "watermark": document.watermark,
            "company_name": document.company_name,
            "page_header": "DRAFT",
            "composed": sections,
        },
        tmp_path / "notes.docx",
    )
    assert "Charges on assets" in xml
    assert "1AD.28" not in xml
    assert _CHECKLIST.search(xml) is None
    assert "<w:keepLines" in xml or "<w:keepLines/>" in xml
    assert "<w:keepNext" in xml or "<w:keepNext/>" in xml
    assert "A dividend has been recorded for the financial year." in xml
    assert "455,812" in xml


def test_wording_banner_is_once_on_the_cover_in_word(tmp_path: Path) -> None:
    document = replace(_golden(), watermark="FINAL")
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    header, signature = docx_presentation(
        document,
        report_setup=_setup(),
        approval_date=None,
        signing_directors=[],
    )
    assert header == f"DRAFT {WORDING_BANNER}"
    _html, sections = compose_pdf_parts(
        document,
        report_setup=_setup(),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        currency="EUR",
    )
    _xml, headers = _docx_parts(
        {
            "watermark": "FINAL",
            "company_name": document.company_name,
            "page_header": header,
            "signature": signature,
            "composed": sections,
        },
        tmp_path / "banner.docx",
    )
    assert headers
    assert sum(WORDING_BANNER in item for item in headers) == 1
    assert all("DRAFT" in item and "FINAL" not in item for item in headers)


def test_dividend_placeholder_and_statement_print_in_pdf_and_word(
    tmp_path: Path,
) -> None:
    unanswered = _report(None)
    assert "[dividend not recorded]" in unanswered
    assert "500" not in unanswered
    none = _report(Decimal("0.00"))
    assert none.count("No dividend has been recorded for the financial year.") == 1
    assert "[dividend not recorded]" not in none
    paid = _report(Decimal("500.00"))
    assert "A dividend has been recorded for the financial year." in paid
    assert "500" not in paid
    assert "[dividend not recorded]" not in paid
    for label, dividends in (
        ("open", None),
        ("paid", Decimal("500.00")),
    ):
        sentence = _report(dividends)
        html = render_statutory_html(
            company_name="Harbour Limited",
            sections=[
                {
                    "kind": "prose",
                    "anchor": "directors-report",
                    "heading": "Directors' report",
                    "paragraphs": sentence.split("\n"),
                }
            ],
            watermark="DRAFT",
        )
        assert sentence.split("\n")[-1] in _pdf_text(html)
        xml, _headers = _docx_parts(
            {
                "watermark": "DRAFT",
                "company_name": "Harbour Limited",
                "page_header": "DRAFT",
                "composed": [
                    {
                        "kind": "prose",
                        "anchor": "directors-report",
                        "heading": "Directors' report",
                        "paragraphs": sentence.split("\n"),
                        "page_break": False,
                    }
                ],
            },
            tmp_path / f"dividend-{label}.docx",
        )
        assert sentence.split("\n")[-1] in xml
