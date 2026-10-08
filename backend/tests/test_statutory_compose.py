"""PDF composer: include list and report-setup display. Figures stay exact."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.draft_workflow import _can_finalise
from app.services.statutory_compose import (
    NOT_BUILT_LINE,
    compose_pdf_html,
    unbuilt_section_notices,
)
from app.services.statutory_present import statement_response
from app.services.statutory_statements import (
    StatementRow,
    StatutoryStatements,
    write_statement_pdf,
)
from findraft.models.year_end import YearEnd
from tests.conftest import auth_headers
from tests.test_adopted_trial_balance import _insert_tb
from tests.test_statutory_display import _pdf_pages
from tests.test_statutory_statements import _golden

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


def test_unset_report_setup_keeps_the_engine_html() -> None:
    document = _golden()
    assert document.html is not None
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert _compose(document, None) == document.html
    assert "in thousands" not in document.html
    assert NOT_BUILT_LINE not in document.html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_matching_display_settings_reprint_the_engine_html() -> None:
    document = _golden()
    assert document.html is not None
    reprinted = _compose(document, _setup())
    assert reprinted == document.html
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
    assert "<h2>Compilation report</h2>" in hidden
    assert "<h2>Income statement</h2>" in hidden
    assert "<h2>Statement of financial position</h2>" in hidden
    assert "<h2>Notes</h2>" in hidden
    assert "<h2>Approval of the financial statements</h2>" in hidden
    assert "455,812" in hidden
    assert "157,650" in hidden
    restored = _compose(document, _setup(sections={"directors-report": True}))
    assert "<h2>Directors&#39; report</h2>" in restored
    assert "<h2>Compilation report</h2>" in restored
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
    assert "<h2>Income statement</h2>" in html
    assert "<h2>Statement of financial position</h2>" in html
    assert "<h2>Notes</h2>" in html
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


def test_pages_that_are_not_built_yet_are_not_placeholders() -> None:
    document = _golden()
    html = _compose(document, _setup())
    assert "<h2>Cover</h2>" not in html
    assert "<h2>Contents</h2>" not in html
    assert "<h2>Directors and other information</h2>" not in html
    assert "<h2>Directors' responsibilities statement</h2>" not in html
    assert NOT_BUILT_LINE not in html


def test_an_enabled_unbuilt_section_is_one_page_without_figures() -> None:
    document = _golden()
    html = _compose(
        document,
        _setup(sections={"cash-flow": True, "oci": True, "trading": False}),
    )
    assert "<h2>Cash flow statement</h2>" in html
    assert "<h2>Statement of comprehensive income</h2>" in html
    assert "<h2>Supplementary trading statement</h2>" not in html
    assert html.count(NOT_BUILT_LINE) == 2
    assert 'data-section="cash-flow"' in html
    assert "page-break-before: always" in html
    assert html.index("<h2>Income statement</h2>") < html.index(
        "<h2>Statement of comprehensive income</h2>"
    )
    assert html.index("<h2>Statement of comprehensive income</h2>") < html.index(
        "<h2>Statement of financial position</h2>"
    )
    assert html.index("<h2>Statement of financial position</h2>") < html.index(
        "<h2>Cash flow statement</h2>"
    )
    assert html.index("<h2>Cash flow statement</h2>") < html.index("<h2>Notes</h2>")
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
    year_end.report_setup = {"sections": {"cash-flow": True, "oci": True, "cover": False}}
    notices = unbuilt_section_notices(year_end)
    assert len(notices) == 1
    assert notices[0].code == "V-SEC-005"
    assert notices[0].severity == "NOTICE"
    assert notices[0].passed is False
    assert "Cash flow statement" in notices[0].message
    assert "Statement of comprehensive income" in notices[0].message
    assert "does not build" in notices[0].message
    assert _can_finalise(
        "amber", renderable=True, blocked=False, checks=notices
    )


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
    assert "<h2>Cash flow statement</h2>" in captured[1]
    assert NOT_BUILT_LINE in captured[1]
    assert "<h2>Income statement</h2>" in captured[1]
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
    assert "<h2>Cash flow statement</h2>" not in captured[2]
    assert after.json()["net_assets"] == "18400.40"


def test_write_statement_pdf_is_unchanged_for_the_engine_html() -> None:
    """The composer does not replace the PDF writer. Engine HTML still renders."""
    document = _golden()
    assert document.html is not None
    pdf = write_statement_pdf(document.html)
    assert pdf.startswith(b"%PDF")
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
