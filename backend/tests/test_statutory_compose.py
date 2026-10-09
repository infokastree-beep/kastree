"""PDF composer: include list and report-setup display. Figures stay exact."""

from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.draft_workflow import _can_finalise
from app.services.report_setup import default_report_setup
from app.services.statutory_compose import (
    DIRECTORS_RESPONSIBILITIES,
    NOT_BUILT_LINE,
    CompanyLetterhead,
    compose_pdf_html,
    pack_display_notices,
    unbuilt_section_notices,
)
from app.services.statutory_present import statement_response
from app.services.statutory_statements import (
    StatementRow,
    StatutoryStatements,
    write_statement_pdf,
)
from findraft.models.year_end import YearEnd
from tests.conftest import auth_headers, make_access_token
from tests.test_adopted_trial_balance import _insert_tb
from tests.test_findraft_tenant_isolation import _delete_org, _provision
from tests.test_organisations_api import _add_org_user
from tests.test_statutory_display import _pdf_pages
from tests.test_statutory_statements import _golden

_OPTIONAL = (
    "cover",
    "contents",
    "directors-info",
    "directors-report",
    "directors-responsibilities",
    "compilation",
)
_FORBIDDEN = "You don't have permission to access this resource."

_ROOT = Path(__file__).resolve().parents[1]
_ENGINE = _ROOT.parent / "findraft" / "engine"


def _setup(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "rounding": "unit",
        "statement_type": "draft",
        "face_dates": {
            "current_start": "2025-01-01",
            "current_end": "2025-12-31",
            "prior_start": None,
            "prior_end": None,
        },
        "column_headers": {
            "as_at_current": "2025 €",
            "as_at_prior": "2024 €",
            "ended_current": "2025 €",
            "ended_prior": "2024 €",
        },
    }
    payload.update(overrides)
    return payload


def _compose(document: object, setup: object | None) -> str:
    from app.services.statutory_statements import StatutoryStatements

    assert isinstance(document, StatutoryStatements)
    return compose_pdf_html(
        document,
        report_setup=setup,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
    )


def _row(html: str, label: str) -> str:
    needle = f"<tr><td>{label}</td>"
    start = html.index(needle)
    end = html.index("</tr>", start)
    return html[start:end]


def test_unset_report_setup_adds_the_default_pages_and_keeps_engine_html() -> None:
    document = _golden()
    assert document.html is not None
    engine = document.html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    html = _compose(document, None)
    assert document.html == engine
    assert ">Financial statements</h2>" in html
    assert ">Contents</h2>" in html
    assert ">Directors and other information</h2>" in html
    assert ">Directors&#39; responsibilities statement</h2>" in html
    assert "2025 €" in html
    assert "455,812" in html
    assert "in thousands" not in document.html
    assert NOT_BUILT_LINE not in html
    assert "source not confirmed" not in html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_matching_display_settings_keep_the_engine_figures() -> None:
    document = _golden()
    assert document.html is not None
    engine = document.html
    reprinted = _compose(document, _setup())
    assert document.html == engine
    assert "455,812" in reprinted
    assert "157,650" in reprinted
    assert ">Financial statements</h2>" in reprinted
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_a_built_section_drops_out_and_comes_back() -> None:
    document = _golden()
    assert document.html is not None
    profit = document.profit
    net_assets = document.net_assets
    hidden = _compose(
        document,
        _setup(sections={"directors-report": False, "compilation": True}),
    )
    assert "Directors&#39; report" not in hidden
    assert ">Compilation report</h2>" in hidden
    assert ">Income statement</h2>" in hidden
    assert ">Statement of financial position</h2>" in hidden
    assert ">Notes</h2>" in hidden
    assert ">Approval of the financial statements</h2>" in hidden
    assert "455,812" in hidden
    assert "157,650" in hidden
    restored = _compose(document, _setup(sections={"directors-report": True}))
    assert ">Directors&#39; report</h2>" in restored
    assert ">Compilation report</h2>" in restored
    assert document.profit == profit == Decimal("157650.00")
    assert document.net_assets == net_assets == Decimal("455812.00")
    assert statement_response(document).profit == "157650.00"
    assert statement_response(document).net_assets == "455812.00"


def test_a_locked_section_stays_when_a_stored_map_says_off() -> None:
    document = _golden()
    html = _compose(
        document,
        _setup(sections={"income": False, "sofp": False, "notes": False}),
    )
    assert ">Income statement</h2>" in html
    assert ">Statement of financial position</h2>" in html
    assert ">Notes</h2>" in html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_cover_contents_and_directors_pages_are_in_the_pdf() -> None:
    document = _golden()
    html = _compose(document, _setup())
    assert ">Cover</h2>" not in html
    assert ">Financial statements</h2>" in html
    assert ">Contents</h2>" in html
    assert ">Directors and other information</h2>" in html
    assert ">Directors&#39; responsibilities statement</h2>" in html
    assert NOT_BUILT_LINE not in html
    assert html.index(">Financial statements</h2>") < html.index(">Contents</h2>")
    assert html.index(">Contents</h2>") < html.index(
        ">Directors and other information</h2>"
    )
    assert html.index(">Directors and other information</h2>") < html.index(
        ">Directors&#39; report</h2>"
    )
    assert html.index(">Directors&#39; report</h2>") < html.index(
        ">Directors&#39; responsibilities statement</h2>"
    )
    assert html.index(">Directors&#39; responsibilities statement</h2>") < html.index(
        ">Compilation report</h2>"
    )
    assert html.index(">Compilation report</h2>") < html.index(">Income statement</h2>")


def _heading_page(pages: list[str], heading: str) -> int:
    for index, page in enumerate(pages, start=1):
        lines = [line.strip() for line in page.splitlines()]
        if heading in lines:
            return index
    raise AssertionError(heading)


def _page_number_shown(page: str, number: int) -> bool:
    token = str(number)
    return any(line.split()[-1:] == [token] for line in page.splitlines())


_NOTES_FOOTER = "The notes form part of these financial statements"
_FLOWING = (
    "Directors' report",
    "Directors' responsibilities statement",
    "Approval of the financial statements",
    "Audit exemption",
)


def _contents_entries(html: str) -> list[tuple[str, str]]:
    """Anchor and visible label for every contents row, in pack order."""
    import html as html_lib

    marker = '<section data-section="contents"'
    start = html.index(marker)
    block = html[start : html.index("</section>", start)]
    found = re.findall(r'href="#([^"]+)">([^<]+)</a>', block)
    assert found
    return [(anchor, html_lib.unescape(label)) for anchor, label in found]


def _anchor_pages(html: str) -> tuple[dict[str, int], bytes, int]:
    """Page each id lands on, from the same render that writes the PDF."""
    from weasyprint import HTML

    from app.services.statutory_statements import _abort_on_fetch

    rendered = HTML(string=html, url_fetcher=_abort_on_fetch).render()
    found: dict[str, int] = {}
    for number, page in enumerate(rendered.pages, start=1):
        for name in page.anchors:
            found.setdefault(str(name), number)
    payload = rendered.write_pdf()
    if not isinstance(payload, bytes):
        raise AssertionError("statement PDF was not produced")
    return found, payload, len(rendered.pages)


def _printed_contents_number(text: str, label: str) -> int:
    """The number printed after a contents label. Words may wrap."""
    words = r"\s+".join(re.escape(word) for word in label.split())
    match = re.search(words + r"\s+(\d+)\b", text)
    if match is None:
        raise AssertionError(label)
    return int(match.group(1))


def test_contents_page_numbers_match_the_pages() -> None:
    """Each contents number is the page that heading is on, whatever the font."""
    document = _golden()
    html = _compose(document, _setup())
    anchors, payload, rendered_pages = _anchor_pages(html)
    pages = _pdf_pages(payload)
    if pages and pages[-1] == "":
        pages.pop()
    assert len(pages) == rendered_pages
    contents_at = anchors["contents"]
    contents_text = "\n".join(pages[contents_at - 1 : contents_at + 1])
    assert "Financial statements" not in pages[contents_at - 1]
    entries = _contents_entries(html)
    assert entries
    for anchor, label in entries:
        assert anchor in anchors, anchor
        assert _printed_contents_number(contents_text, label) == anchors[anchor], label
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_cover_prints_the_company_number_without_a_footer_or_page_number() -> None:
    document = _golden()
    html = compose_pdf_html(
        document,
        report_setup=_setup(),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        letterhead=CompanyLetterhead(company_number="AB123456"),
    )
    assert "Company number: AB123456" in html
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    cover = pages[0]
    assert "Financial statements" in cover
    assert "Company number: AB123456" in cover
    assert "DRAFT" in cover
    assert _NOTES_FOOTER not in cover
    assert _page_number_shown(cover, 1) is False
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_notes_footer_and_page_numbers_follow_the_page() -> None:
    document = _golden()
    html = _compose(document, _setup())
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    notes_at = _heading_page(pages, "Notes")
    for index, page in enumerate(pages, start=1):
        assert "DRAFT" in page
        if index == 1:
            assert _NOTES_FOOTER not in page
            assert _page_number_shown(page, 1) is False
            continue
        assert _page_number_shown(page, index), index
        statement_page = (
            any(line.strip() == "Income statement" for line in page.splitlines())
            or any(
                line.strip() == "Statement of financial position"
                for line in page.splitlines()
            )
            or index >= notes_at
        )
        if statement_page:
            assert _NOTES_FOOTER in page, index
        else:
            assert _NOTES_FOOTER not in page, index
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_short_sections_share_a_page() -> None:
    """Short narrative sections share a sheet. The sheet count follows the font."""
    document = _golden()
    html = _compose(document, _setup())
    assert 'data-section="directors-report"' in html
    report = html.split('data-section="directors-report"', 1)[1].split(">", 1)[0]
    assert "page-break-before" not in report
    cash = html.split('data-section="income"', 1)[1].split(">", 1)[0]
    assert "page-break-before" in cash
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    flowing_pages = {_heading_page(pages, heading) for heading in _FLOWING}
    assert len(flowing_pages) < len(_FLOWING)
    forced = (
        "Financial statements",
        "Contents",
        "Directors and other information",
        "Compilation report",
        "Income statement",
        "Statement of financial position",
        "Notes",
    )
    starts = [_heading_page(pages, heading) for heading in forced]
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_directors_responsibilities_cite_no_act_section() -> None:
    document = _golden()
    html = _compose(document, _setup())
    marker = '<section data-section="directors-responsibilities"'
    block = html[html.index(marker) : html.index("<section", html.index(marker) + 1)]
    assert DIRECTORS_RESPONSIBILITIES.replace("'", "&#39;") in block
    assert "source not confirmed" not in block
    assert "Companies Act" not in block
    assert re.search(r"section\s+\d+", block, flags=re.IGNORECASE) is None
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    page = pages[_heading_page(pages, "Directors' responsibilities statement") - 1]
    flat = " ".join(page.split())
    assert DIRECTORS_RESPONSIBILITIES in flat
    assert "Companies Act" not in page
    assert "source not confirmed" not in page
    assert re.search(r"section\s+\d+", page, flags=re.IGNORECASE) is None
    workspace = (
        _ROOT.parent
        / "frontend"
        / "components"
        / "statutory"
        / "CompanyDetailsForm.tsx"
    ).read_text(encoding="utf-8")
    assert 'data-testid="directors-responsibilities-source"' in workspace
    assert "source not confirmed" in workspace
    assert DIRECTORS_RESPONSIBILITIES in workspace
    pack = (_ROOT.parent / "findraft/content/frs102-1a-ie/2024.09/pack.json").read_text(
        encoding="utf-8"
    )
    compose_source = (_ROOT / "app/services/statutory_compose.py").read_text(
        encoding="utf-8"
    )
    assert "DIRECTORS_RESPONSIBILITIES = (" in compose_source
    assert "safeguarding the assets" in compose_source
    assert "safeguarding the assets" not in pack
    lowered = DIRECTORS_RESPONSIBILITIES.casefold()
    assert "accounting policies" not in lowered
    assert "prudent" not in lowered
    assert "going concern" not in lowered
    assert "accounting records" in lowered
    assert "safeguarding" in lowered


def test_advisers_print_on_the_directors_page() -> None:
    document = _golden()
    html = compose_pdf_html(
        document,
        report_setup=_setup(),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
        letterhead=CompanyLetterhead(
            registered_office="1 Harbour Street",
            business_address="Unit 2\nDock Road",
            company_number="AB123456",
            incorporated_on=date(2018, 3, 14),
            secretary="Grace Hopper",
            directors=({"name": "Ada Lovelace", "appointed_on": "2020-03-01"},),
            advisers=({"role": "Bankers", "name": "AIB"},),
        ),
    )
    assert "Registered office: 1 Harbour Street" in html
    assert "Business address: Unit 2, Dock Road" in html
    assert "Company number: AB123456" in html
    assert "Date of incorporation: 14 March 2018" in html
    assert "Company secretary: Grace Hopper" in html
    assert "Ada Lovelace (appointed 1 March 2020)" in html
    assert "Advisers: Bankers: AIB." in html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_an_enabled_unbuilt_section_is_one_page_without_figures() -> None:
    document = _golden()
    html = _compose(
        document,
        _setup(sections={"cash-flow": True, "oci": True, "trading": False}),
    )
    assert ">Cash flow statement</h2>" in html
    assert ">Statement of comprehensive income</h2>" in html
    assert ">Supplementary trading statement</h2>" not in html
    assert html.count(NOT_BUILT_LINE) == 2
    assert 'data-section="cash-flow"' in html
    assert "page-break-before: always" in html
    assert html.index(">Income statement</h2>") < html.index(
        ">Statement of comprehensive income</h2>"
    )
    assert html.index(">Statement of comprehensive income</h2>") < html.index(
        ">Statement of financial position</h2>"
    )
    assert html.index(">Statement of financial position</h2>") < html.index(
        ">Cash flow statement</h2>"
    )
    assert html.index(">Cash flow statement</h2>") < html.index(">Notes</h2>")
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert "455812.00" not in html
    assert "157650.00" not in html


def test_thousands_heading_uses_a_new_string_and_leaves_the_decimal() -> None:
    document = _golden()
    profit = document.profit
    net_assets = document.net_assets
    assert profit == Decimal("157650.00")
    assert net_assets == Decimal("455812.00")
    html = _compose(
        document,
        _setup(
            rounding="thousands",
            column_headers={
                "as_at_current": "2025",
                "as_at_prior": "2024",
                "ended_current": "2025",
                "ended_prior": "2024",
            },
        ),
    )
    assert "2025 in thousands" in html
    assert "2024 in thousands" in html
    assert ">158<" in _row(html, "Profit for the financial year")
    assert ">456<" in _row(html, "Net assets")
    assert profit == Decimal("157650.00")
    assert net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert document.net_assets == Decimal("455812.00")
    assert statement_response(document).profit == "157650.00"
    assert statement_response(document).net_assets == "455812.00"


def test_face_dates_and_compilation_label_do_not_change_figures() -> None:
    document = _golden()
    html = _compose(
        document,
        _setup(
            statement_type="compilation",
            face_dates={
                "current_start": "2024-04-01",
                "current_end": "2025-12-31",
                "prior_start": None,
                "prior_end": None,
            },
        ),
    )
    assert '<p class="watermark">DRAFT Compilation</p>' in html
    assert '<p class="watermark">COMPILATION</p>' not in html
    assert "COMPILATION" not in html
    assert '<p class="watermark">AUDIT</p>' not in html
    assert '<p class="watermark">REVIEW</p>' not in html
    assert "for the period from 1 April 2024 to 31 December 2025" in html
    assert "as at 31 December 2025" in html
    assert "Trial balance period: for the year ended 31 December 2025." in html
    assert document.watermark == "DRAFT"
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


@pytest.mark.parametrize("statement_type", ["draft", "compilation"])
def test_an_unsigned_draft_keeps_draft_on_every_page(statement_type: str) -> None:
    """DRAFT stays on the cover line and the page header. Compilation sits beside it."""
    document = _golden()
    assert document.watermark == "DRAFT"
    html = _compose(document, _setup(statement_type=statement_type))
    assert "COMPILATION" not in html
    assert '<p class="watermark">COMPILATION</p>' not in html
    if statement_type == "compilation":
        assert '<p class="watermark">DRAFT Compilation</p>' in html
        assert 'content: "DRAFT Compilation"' in html
    else:
        assert '<p class="watermark">DRAFT</p>' in html
        assert 'content: "DRAFT"' in html
        assert 'content: "DRAFT Compilation"' not in html
        assert '<p class="watermark">DRAFT Compilation</p>' not in html
    assert document.watermark == "DRAFT"
    assert statement_response(document).watermark == "DRAFT"
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    assert len(pages) > 1
    for page in pages:
        assert "DRAFT" in page
        assert "COMPILATION" not in page
        if statement_type == "compilation":
            assert "DRAFT Compilation" in page
        else:
            assert "DRAFT Compilation" not in page


def test_a_finalised_document_keeps_final_and_does_not_say_compilation() -> None:
    document = _golden()
    final = StatutoryStatements(
        watermark="FINAL",
        renderable=document.renderable,
        blocked=document.blocked,
        build_error=document.build_error,
        checks=document.checks,
        net_assets=document.net_assets,
        profit=document.profit,
        compliance_statement=document.compliance_statement,
        sofp=document.sofp,
        income=document.income,
        notes=document.notes,
        rounding_flags=document.rounding_flags,
        html=document.html,
        pages=document.pages,
        company_name=document.company_name,
    )
    html = _compose(final, _setup(statement_type="compilation"))
    assert '<p class="watermark">FINAL</p>' in html
    assert 'content: "FINAL"' in html
    assert "DRAFT" not in html
    assert "COMPILATION" not in html
    assert '<p class="watermark">FINAL Compilation</p>' not in html
    assert final.watermark == "FINAL"
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_thousands_prints_a_rounding_difference_when_lines_do_not_foot() -> None:
    """600 and 600 display as 1 and 1. Their total of 1200 displays as 1.

    The PDF prints a Rounding difference of (1) so the column foots.
    The source Decimals stay 600, 600, and 1200.
    """
    turnover = StatementRow("Turnover", Decimal("600.00"), None)
    cost = StatementRow("Cost of sales", Decimal("600.00"), None)
    gross = StatementRow("Gross profit", Decimal("1200.00"), None)
    document = StatutoryStatements(
        watermark="DRAFT",
        renderable=True,
        blocked=False,
        build_error=None,
        checks=(),
        net_assets=Decimal("1200.00"),
        profit=Decimal("1200.00"),
        compliance_statement="",
        sofp=(),
        income=(turnover, cost, gross),
        notes=(),
        rounding_flags=(),
        html="<p>engine</p>",
        company_name="Example Ltd",
    )

    def _show(setup: dict[str, object]) -> str:
        return compose_pdf_html(
            document,
            report_setup=setup,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 12, 31),
            first_financial_period=True,
        )

    unit = _show(_setup(rounding="unit"))
    assert "Rounding difference" not in unit
    html = _show(
        _setup(
            rounding="thousands",
            column_headers={
                "as_at_current": "2025",
                "as_at_prior": "2024",
                "ended_current": "2025",
                "ended_prior": "2024",
            },
        )
    )
    assert "in thousands" in html
    printed = _row(html, "Rounding difference")
    assert printed == '<tr><td>Rounding difference</td><td class="amount">(1)</td>'
    pages = [page for page in _pdf_pages(write_statement_pdf(html)) if page.strip()]
    assert pages
    assert any("Rounding difference" in page and "(1)" in page for page in pages)
    assert turnover.current == Decimal("600.00")
    assert cost.current == Decimal("600.00")
    assert gross.current == Decimal("1200.00")
    assert document.profit == Decimal("1200.00")
    assert document.net_assets == Decimal("1200.00")


def test_unbuilt_section_notice_does_not_block_final() -> None:
    quiet = YearEnd()
    quiet.report_setup = None
    assert unbuilt_section_notices(quiet) == ()
    year_end = YearEnd()
    year_end.report_setup = {
        "sections": {"cash-flow": True, "oci": True, "cover": False}
    }
    notices = unbuilt_section_notices(year_end)
    assert len(notices) == 1
    assert notices[0].code == "V-SEC-005"
    assert notices[0].severity == "NOTICE"
    assert notices[0].passed is False
    assert "Cash flow statement" in notices[0].message
    assert "Statement of comprehensive income" in notices[0].message
    assert "does not build" in notices[0].message
    assert _can_finalise("amber", renderable=True, blocked=False, checks=notices)


def test_engine_sources_do_not_import_the_composer() -> None:
    for path in _ENGINE.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "report_setup" not in source
        assert "statutory_compose" not in source
    statements = (_ROOT / "app" / "services" / "statutory_statements.py").read_text(
        encoding="utf-8"
    )
    assert "report_setup" not in statements
    assert "statutory_compose" not in statements
    workflow = (_ROOT / "app" / "services" / "draft_workflow.py").read_text(
        encoding="utf-8"
    )
    assert "report_setup" not in workflow


@pytest.mark.asyncio
async def test_downloaded_pdf_follows_the_include_list(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    company_id = provisioned_org["company_id"]
    assert isinstance(company_id, uuid.UUID)
    token = provisioned_org["token"]
    assert isinstance(token, str)
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2130", "Bank current account", "18400.40", "0.00", "18400.40", "cash"),
            (
                "3000",
                "Called up share capital",
                "0.00",
                "18400.40",
                "-18400.40",
                "share_capital",
            ),
        ),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )
    headers = auth_headers(token)
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    gate = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert gate.status_code == 200, gate.text
    captured: list[str] = []

    def _capture(html: str) -> bytes:
        captured.append(html)
        return b"%PDF-1.7 captured"

    monkeypatch.setattr("app.routers.year_ends.write_statement_pdf", _capture)
    first = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert "Directors&#39; report" in captured[0]
    assert NOT_BUILT_LINE not in captured[0]
    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    assert before.json()["net_assets"] == "18400.40"

    def _body(sections: dict[str, bool]) -> dict[str, object]:
        return {
            "rounding": "unit",
            "statement_type": "draft",
            "face_dates": {
                "current_start": "2026-01-01",
                "current_end": "2026-12-31",
                "prior_start": None,
                "prior_end": None,
            },
            "column_headers": {
                "as_at_current": "2026",
                "as_at_prior": "2025",
                "ended_current": "2026",
                "ended_prior": "2025",
            },
            "sections": sections,
        }

    hidden = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_body({"directors-report": False, "cash-flow": True}),
    )
    assert hidden.status_code == 200, hidden.text
    second = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert second.status_code == 200, second.text
    assert "Directors&#39; report" not in captured[1]
    assert ">Cash flow statement</h2>" in captured[1]
    assert NOT_BUILT_LINE in captured[1]
    assert ">Income statement</h2>" in captured[1]
    after = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert after.json()["net_assets"] == "18400.40"
    assert after.json()["profit"] == before.json()["profit"]

    shown = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_body({"directors-report": True, "cash-flow": False}),
    )
    assert shown.status_code == 200, shown.text
    third = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert third.status_code == 200, third.text
    assert "Directors&#39; report" in captured[2]
    assert ">Cash flow statement</h2>" not in captured[2]
    assert after.json()["net_assets"] == "18400.40"


def _display(
    headers: dict[str, str], sections: dict[str, bool] | None = None
) -> dict[str, object]:
    payload: dict[str, object] = {
        "rounding": "unit",
        "statement_type": "draft",
        "face_dates": {
            "current_start": "2026-01-01",
            "current_end": "2026-12-31",
            "prior_start": None,
            "prior_end": None,
        },
        "column_headers": headers,
    }
    if sections is not None:
        payload["sections"] = sections
    return payload


def _symbol_headers() -> dict[str, str]:
    return {
        "as_at_current": "2026 £",
        "as_at_prior": "2025 £",
        "ended_current": "2026 £",
        "ended_prior": "2025 £",
    }


def _year_headers() -> dict[str, str]:
    return {
        "as_at_current": "2026",
        "as_at_prior": "2025",
        "ended_current": "2026",
        "ended_prior": "2025",
    }


def _checks(body: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = body["checks"]
    assert isinstance(raw, list)
    return {item["code"]: item for item in raw if isinstance(item, dict)}


def _year_column_headers(html: str) -> list[str]:
    return [
        item
        for item in re.findall(r'<th class="amount">([^<]+)</th>', html)
        if item[:4].isdigit()
    ]


async def _open_draft(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> tuple[str, dict[str, str], uuid.UUID]:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    token = provisioned_org["token"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    assert isinstance(token, str)
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2130", "Bank current account", "18400.40", "0.00", "18400.40", "cash"),
            (
                "3000",
                "Called up share capital",
                "0.00",
                "18400.40",
                "-18400.40",
                "share_capital",
            ),
        ),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )
    headers = auth_headers(token)
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    assert isinstance(year_end_id, str)
    gate = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert gate.status_code == 200, gate.text
    return year_end_id, headers, org_id


async def _pdf_html(
    api_client: AsyncClient,
    year_end_id: str,
    headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    captured: list[str] = []

    def _capture(html: str) -> bytes:
        captured.append(html)
        return b"%PDF-1.7 captured"

    monkeypatch.setattr("app.routers.year_ends.write_statement_pdf", _capture)
    response = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert captured
    return captured[-1]


def test_saved_default_headers_keep_the_currency_symbol() -> None:
    """A save of the displayed defaults keeps the symbol on the face and in notes."""
    document = _golden()
    year_end = YearEnd()
    year_end.period_start = date(2025, 1, 1)
    year_end.period_end = date(2025, 12, 31)
    setup = default_report_setup(year_end, "EUR")
    html = _compose(document, setup.model_dump(mode="json"))
    income = html.index('id="income"')
    sofp = html.index('id="sofp"')
    assert '<th class="amount">2025 €</th>' in html[income:sofp]
    debtors = html.index('id="note-N3_DEBTORS"')
    assert '<th class="amount">2025 €</th>' in html[debtors : debtors + 1500]
    assert 'content: "DRAFT"' in html
    for anchor in _OPTIONAL:
        assert f'id="{anchor}"' in html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_pack_display_notices_name_switched_off_sections_and_header_drift() -> None:
    quiet = YearEnd()
    quiet.period_start = date(2026, 1, 1)
    quiet.period_end = date(2026, 12, 31)
    quiet.report_setup = None
    assert pack_display_notices(quiet, "GBP") == ()
    bare = YearEnd()
    assert pack_display_notices(bare, "GBP") == ()
    drifted = YearEnd()
    drifted.period_start = date(2026, 1, 1)
    drifted.period_end = date(2026, 12, 31)
    drifted.report_setup = _display(
        _year_headers(), {section_id: False for section_id in _OPTIONAL}
    )
    notices = pack_display_notices(drifted, "GBP")
    assert [item.code for item in notices] == ["V-SEC-006", "V-SEC-007"]
    assert notices[0].severity == "NOTICE"
    assert notices[0].passed is False
    assert notices[0].message == (
        "6 sections are switched off: Cover, Contents, "
        "Directors and other information, Directors' report, "
        "Directors' responsibilities statement, Compilation report"
    )
    assert notices[1].message == "Report setup differs from defaults: column headers"
    assert _can_finalise("amber", renderable=True, blocked=False, checks=notices)
    cash_only = YearEnd()
    cash_only.period_start = date(2026, 1, 1)
    cash_only.period_end = date(2026, 12, 31)
    cash_only.report_setup = _display(_symbol_headers(), {"cash-flow": False})
    assert pack_display_notices(cash_only, "GBP") == ()


@pytest.mark.asyncio
async def test_no_saved_setup_includes_the_six_optional_sections(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id, headers, _org_id = await _open_draft(api_client, provisioned_org)
    setup = await api_client.get(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
    )
    assert setup.status_code == 200, setup.text
    body = setup.json()
    assert body["sections"] is None
    assert body["column_headers"] == _symbol_headers()
    html = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    for anchor in _OPTIONAL:
        assert f'id="{anchor}"' in html
    assert _year_column_headers(html)
    assert all("£" in item for item in _year_column_headers(html))
    assert 'content: "DRAFT"' in html
    figures = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert figures.status_code == 200, figures.text
    assert figures.json()["net_assets"] == "18400.40"


@pytest.mark.asyncio
async def test_empty_sections_map_is_not_stored_as_all_false(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id, headers, _org_id = await _open_draft(api_client, provisioned_org)
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display(_symbol_headers(), {}),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["sections"] is None
    html = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    for anchor in _OPTIONAL:
        assert f'id="{anchor}"' in html


@pytest.mark.asyncio
async def test_reset_restores_sections_and_symbol_and_notices_track_them(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id, headers, org_id = await _open_draft(api_client, provisioned_org)
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    draft_id = draft.json()["draft_id"]

    async def board() -> dict[str, dict[str, object]]:
        response = await api_client.get(
            f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        return _checks(response.json())

    quiet = await board()
    assert "V-SEC-006" not in quiet
    assert "V-SEC-007" not in quiet
    hidden = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display(
            _symbol_headers(), {section_id: False for section_id in _OPTIONAL}
        ),
    )
    assert hidden.status_code == 200, hidden.text
    sections_off = await board()
    assert "V-SEC-006" in sections_off
    assert sections_off["V-SEC-006"]["passed"] is False
    assert sections_off["V-SEC-006"]["severity"] == "NOTICE"
    assert "6 sections are switched off:" in str(sections_off["V-SEC-006"]["message"])
    assert "V-SEC-007" not in sections_off
    missing = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    for anchor in _OPTIONAL:
        assert f'id="{anchor}"' not in missing
    assert 'content: "DRAFT"' in missing
    drifted = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display(_year_headers(), {section_id: False for section_id in _OPTIONAL}),
    )
    assert drifted.status_code == 200, drifted.text
    both = await board()
    assert "V-SEC-006" in both
    assert both["V-SEC-007"]["message"] == (
        "Report setup differs from defaults: column headers"
    )
    bare = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    assert _year_column_headers(bare)
    assert all("£" not in item for item in _year_column_headers(bare))
    restored_sections = await api_client.post(
        f"/year-ends/{year_end_id}/report-setup/reset",
        headers=headers,
        json={"scope": "sections"},
    )
    assert restored_sections.status_code == 200, restored_sections.text
    assert restored_sections.json()["sections"] is None
    after_sections = await board()
    assert "V-SEC-006" not in after_sections
    assert "V-SEC-007" in after_sections
    back = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    for anchor in _OPTIONAL:
        assert f'id="{anchor}"' in back
    restored_display = await api_client.post(
        f"/year-ends/{year_end_id}/report-setup/reset",
        headers=headers,
        json={"scope": "display"},
    )
    assert restored_display.status_code == 200, restored_display.text
    assert restored_display.json()["column_headers"] == _symbol_headers()
    cleared = await board()
    assert "V-SEC-006" not in cleared
    assert "V-SEC-007" not in cleared
    symbol = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    assert _year_column_headers(symbol)
    assert all("£" in item for item in _year_column_headers(symbol))
    assert 'content: "DRAFT"' in symbol
    figures = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert figures.json()["net_assets"] == "18400.40"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE org_id = :org "
                "AND action = 'report_setup_reset'"
            ),
            {"org": str(org_id)},
        ).scalar_one()
    assert count == 2


@pytest.mark.asyncio
async def test_viewer_cannot_reset_and_another_practice_is_not_found(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    year_end_id, _headers, org_id = await _open_draft(api_client, provisioned_org)
    clerk_org_id = provisioned_org["clerk_org_id"]
    assert isinstance(clerk_org_id, str)
    _user_id, _clerk_user_id, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=clerk_org_id,
        role="viewer",
        email_prefix="reset-viewer",
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/report-setup/reset",
        headers=auth_headers(viewer_token),
        json={"scope": "sections"},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN
    suffix = uuid.uuid4().hex[:10]
    other = _provision(suffix)
    try:
        other_token = make_access_token(
            clerk_user_id=f"user_fd_{suffix}",
            clerk_org_id=f"org_fd_{suffix}",
            org_uuid=other["org_id"],
        )
        hidden = await api_client.post(
            f"/year-ends/{year_end_id}/report-setup/reset",
            headers=auth_headers(other_token),
            json={"scope": "display"},
        )
        assert hidden.status_code == 404, hidden.text
        assert hidden.json()["detail"] == "Year end not found"
    finally:
        _delete_org(other["org_id"])


def _section_open(html: str, anchor: str) -> str:
    return html.split(f'data-section="{anchor}"', 1)[1].split(">", 1)[0]


def test_compilation_starts_a_new_page_unless_setup_overrides_it() -> None:
    """The pack default is a new page. A saved map can flow it or force another."""
    from app.services.statutory_compose import extract_section_html, preview_document

    document = _golden()
    html = _compose(document, _setup())
    assert "page-break-before" in _section_open(html, "compilation")
    assert "page-break-before" not in _section_open(html, "directors-report")
    assert "page-break-before" not in _section_open(html, "approval")
    preview = preview_document(html, extract_section_html(html, "compilation") or "")
    assert 'data-section="compilation"' in preview
    assert "page-break-before" in preview
    flowed = _compose(
        document,
        _setup(page_starts={"compilation": False, "directors-report": True}),
    )
    assert "page-break-before" not in _section_open(flowed, "compilation")
    assert "page-break-before" in _section_open(flowed, "directors-report")
    anchors, _payload, _count = _anchor_pages(flowed)
    pages = _pdf_pages(_payload)
    if pages and pages[-1] == "":
        pages.pop()
    contents_at = anchors["contents"]
    contents_text = "\n".join(pages[contents_at - 1 : contents_at + 1])
    for anchor, label in _contents_entries(flowed):
        assert _printed_contents_number(contents_text, label) == anchors[anchor], label
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def _composed_page_count(html: str) -> tuple[dict[str, int], list[str], int]:
    anchors, payload, rendered_pages = _anchor_pages(html)
    pages = _pdf_pages(payload)
    if pages and pages[-1] == "":
        pages.pop()
    assert len(pages) == rendered_pages
    return anchors, pages, rendered_pages


def test_default_page_counts_for_the_golden_and_first_period_files() -> None:
    """Print the composed page counts. The sheet count follows the font.

    Forced sections each start a page, and every contents number is the page
    that heading lands on. The printed counts are the ones for this run.
    """
    from tests.test_statutory_display import _first_period

    forced = (
        "Financial statements",
        "Contents",
        "Directors and other information",
        "Compilation report",
        "Income statement",
        "Statement of financial position",
        "Notes",
    )
    golden = _golden()
    golden_html = _compose(golden, _setup())
    first = _first_period()
    first_html = compose_pdf_html(
        first,
        report_setup=None,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        first_financial_period=True,
        currency="EUR",
    )
    counts: list[int] = []
    for html in (golden_html, first_html):
        anchors, pages, rendered_pages = _composed_page_count(html)
        counts.append(rendered_pages)
        starts = [_heading_page(pages, heading) for heading in forced]
        assert starts == sorted(starts)
        assert len(set(starts)) == len(starts)
        assert rendered_pages >= len(forced)
        contents_at = anchors["contents"]
        contents_text = "\n".join(pages[contents_at - 1 : contents_at + 1])
        for anchor, label in _contents_entries(html):
            assert anchor in anchors, anchor
            assert (
                _printed_contents_number(contents_text, label) == anchors[anchor]
            ), label
    assert golden.net_assets == Decimal("455812.00")
    assert golden.profit == Decimal("157650.00")
    assert first.net_assets == Decimal("35000.00")
    assert first.profit == Decimal("25000.00")
    print(f"golden_pages={counts[0]} first_period_pages={counts[1]}")


@pytest.mark.asyncio
async def test_page_start_is_stored_and_cleared_by_sections_reset(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id, headers, _org_id = await _open_draft(api_client, provisioned_org)
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            **_display(_symbol_headers()),
            "page_starts": {"compilation": False, "income": True},
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["page_starts"] == {"compilation": False}
    assert saved.json()["sections"] is None
    html = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    assert "page-break-before" not in _section_open(html, "compilation")
    kept = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display(_symbol_headers()),
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["page_starts"] == {"compilation": False}
    drifted = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display(_year_headers()),
    )
    assert drifted.status_code == 200, drifted.text
    display_reset = await api_client.post(
        f"/year-ends/{year_end_id}/report-setup/reset",
        headers=headers,
        json={"scope": "display"},
    )
    assert display_reset.status_code == 200, display_reset.text
    assert display_reset.json()["page_starts"] == {"compilation": False}
    assert display_reset.json()["column_headers"] == _symbol_headers()
    restored = await api_client.post(
        f"/year-ends/{year_end_id}/report-setup/reset",
        headers=headers,
        json={"scope": "sections"},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["page_starts"] is None
    assert restored.json()["sections"] is None
    again = await _pdf_html(api_client, year_end_id, headers, monkeypatch)
    assert "page-break-before" in _section_open(again, "compilation")


def test_write_statement_pdf_is_unchanged_for_the_engine_html() -> None:
    """The composer does not replace the PDF writer. Engine HTML still renders."""
    document = _golden()
    assert document.html is not None
    pdf = write_statement_pdf(document.html)
    assert pdf.startswith(b"%PDF")
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
