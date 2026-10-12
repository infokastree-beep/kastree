"""Two directors sign. A sole director signs alone. No new column."""

from __future__ import annotations

import uuid
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.models.company import Company
from app.services.company_details import blocks_final, company_detail_checks
from app.services.statutory_compose import (
    compose_pdf_parts,
    docx_presentation,
    extract_section_html,
)
from app.services.statutory_docx import build_docx
from app.services.statutory_statements import build_statutory_statements
from findraft.models.year_end import YearEnd
from tests.test_reconciliation import _FA_REGISTER, _MAPPINGS, _TB, _lines
from tests.test_statutory_statements import _entity

_PHRASE = "Approved by the board and signed on its behalf by"
_TWO = (
    "Two directors must sign the balance sheet and the directors' report. "
    "Companies Act 2014, sections 324 and 332."
)


def _year() -> YearEnd:
    return YearEnd(
        org_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        period_end=date(2026, 12, 31),
        pack_id="frs102-1a-ie",
        pack_version="2024.09",
    )


def _company(directors: list[dict[str, str | None]]) -> Company:
    return Company(
        client_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        name="Northwind Limited",
        functional_currency="EUR",
        country_of_incorporation="IE",
        directors=directors,
    )


def _signature(company: Company, year_end: YearEnd):
    return next(
        item
        for item in company_detail_checks(company, year_end)
        if item.code == "V-CO-006"
    )


def test_sole_director_signs_alone_and_two_directors_need_two() -> None:
    year_end = _year()
    sole = _company([{"name": "Ada Lovelace", "resigned_on": None}])
    missing = _signature(sole, year_end)
    assert missing.passed is False
    assert missing.message == "A signing director has not been recorded."
    assert blocks_final((missing,)) is True
    year_end.signing_directors = ["Ada Lovelace"]
    recorded = _signature(sole, year_end)
    assert recorded.passed is True
    assert recorded.message == "A signing director is recorded."
    assert blocks_final((recorded,)) is False

    board = _company(
        [
            {"name": "Ada Lovelace", "resigned_on": None},
            {"name": "Grace Hopper", "resigned_on": None},
        ]
    )
    year_end.signing_directors = ["Ada Lovelace"]
    one = _signature(board, year_end)
    assert one.passed is False
    assert one.message == _TWO
    assert blocks_final((one,)) is True
    year_end.signing_directors = ["Ada Lovelace", "Grace Hopper"]
    both = _signature(board, year_end)
    assert both.passed is True
    assert both.message == "Two signing directors are recorded."
    assert blocks_final((both,)) is False

    resigned = _company(
        [
            {"name": "Ada Lovelace", "resigned_on": None},
            {"name": "Grace Hopper", "resigned_on": "2026-06-01"},
        ]
    )
    year_end.signing_directors = ["Ada Lovelace"]
    assert _signature(resigned, year_end).passed is True
    year_end.signing_directors = ["Grace Hopper"]
    former = _signature(resigned, year_end)
    assert former.passed is False
    assert (
        former.message == "The signing director has to be a director still in office."
    )


def _signed():
    return build_statutory_statements(
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
        approval_date="2027-03-15",
        signing_directors="Ada Lovelace, Grace Hopper",
    )


def _has_block(section: str) -> None:
    assert _PHRASE in section
    assert "Approved on 15 March 2027." in section
    assert "Ada Lovelace" in section
    assert "Grace Hopper" in section
    assert "Director" in section


def test_signature_block_is_on_the_directors_report_and_the_balance_sheet(
    tmp_path: Path,
) -> None:
    document = _signed()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert document.html is not None
    engine_report = extract_section_html(document.html, "directors&#39;-report")
    engine_sofp = extract_section_html(document.html, "sofp")
    assert engine_report is not None and engine_sofp is not None
    _has_block(engine_report)
    _has_block(engine_sofp)

    html, sections = compose_pdf_parts(
        document,
        report_setup=None,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        approval_date=date(2027, 3, 15),
        signing_directors=["Ada Lovelace", "Grace Hopper"],
        currency="EUR",
    )
    report = extract_section_html(html, "directors-report")
    sofp = extract_section_html(html, "sofp")
    assert report is not None and sofp is not None
    _has_block(report)
    _has_block(sofp)
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")

    page_header, signature = docx_presentation(
        document,
        report_setup=None,
        approval_date=date(2027, 3, 15),
        signing_directors=["Ada Lovelace", "Grace Hopper"],
    )
    dest = tmp_path / "signed.docx"
    build_docx(
        {
            "watermark": document.watermark,
            "company_name": document.company_name,
            "page_header": page_header,
            "signature": signature,
            "composed": sections,
        },
        dest,
    )
    with zipfile.ZipFile(dest) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    report_at = xml.rindex("Directors' report")
    sofp_at = xml.rindex("Statement of financial position")
    assert report_at < sofp_at
    assert _PHRASE in xml[report_at:sofp_at]
    assert _PHRASE in xml[sofp_at:]
    assert "Ada Lovelace" in xml[report_at:sofp_at]
    assert "Grace Hopper" in xml[sofp_at:]
    assert "Approved on 15 March 2027." in xml[report_at:sofp_at]
    assert "Approved on 15 March 2027." in xml[sofp_at:]
