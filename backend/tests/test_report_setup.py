"""Report setup is display-only, and the sidebar catalogue follows the framework."""

from __future__ import annotations

import inspect
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.routers import year_ends as year_end_router
from app.services import draft_workflow, statutory_present, statutory_statements
from app.services.report_setup import display_amount, save_report_setup, sections_for
from tests.conftest import auth_headers
from tests.test_adopted_trial_balance import _insert_tb

_ROOT = Path(__file__).resolve().parents[1]


def test_display_rounding_returns_a_new_string_and_leaves_the_decimal() -> None:
    amount = Decimal("18400.40")
    assert display_amount(amount, "unit") == "18400"
    assert display_amount(amount, "thousands") == "18"
    assert amount == Decimal("18400.40")

    half = Decimal("10.50")
    assert display_amount(half, "unit") == "11"
    assert half == Decimal("10.50")
    assert display_amount(Decimal("-10.50"), "unit") == "-11"
    assert display_amount(Decimal("18500"), "thousands") == "19"
    assert display_amount(Decimal("-18500"), "thousands") == "-19"


def test_sidebar_sections_follow_the_reporting_framework() -> None:
    frs = [section.label for section in sections_for("frs102-1a-ie")]
    form11 = [section.label for section in sections_for("form11-summary")]
    unknown = [section.label for section in sections_for("uk-frs105")]

    assert frs == [
        "Report setup",
        "Sub-line review",
        "Disclosures",
        "Adjustments",
        "Review dashboard",
        "Income statement",
        "Statement of financial position",
    ]
    assert form11 == [
        "Report setup",
        "Extracts summary",
        "Review dashboard",
    ]
    assert "Sub-line review" not in form11
    assert "Extracts summary" not in frs
    assert len(form11) < len(frs)
    assert unknown == ["Report setup", "Review dashboard"]
    assert unknown != frs


def test_statement_build_does_not_read_report_setup() -> None:
    for module in (statutory_statements, statutory_present, draft_workflow):
        source = inspect.getsource(module)
        assert "report_setup" not in source
    save_source = inspect.getsource(save_report_setup)
    assert "statements_for_adopted" not in save_source
    assert "recompute" not in save_source


def _snapshot(org_id: uuid.UUID, year_end_id: str) -> tuple[object, ...]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text(
                """
                SELECT ye.period_start::text,
                       ye.period_end::text,
                       ye.pack_id,
                       ye.pack_version,
                       ye.adopted_trial_balance_id::text,
                       ye.prior_year_validated,
                       ye.first_financial_period,
                       d.row_version,
                       md5(tb.parsed_data::text)
                FROM findraft_year_ends ye
                JOIN findraft_draft_versions d
                  ON d.year_end_id = ye.id
                JOIN trial_balances tb
                  ON tb.id = ye.adopted_trial_balance_id
                WHERE ye.id = :id
                ORDER BY d.version_number DESC
                LIMIT 1
                """
            ),
            {"id": year_end_id},
        ).one()
    return tuple(row)


def _figures(body: dict[str, object]) -> dict[str, object]:
    def rows(name: str) -> list[tuple[object, object, object]]:
        raw = body[name]
        assert isinstance(raw, list)
        return [
            (row["label"], row["current"], row["prior"])
            for row in raw
            if isinstance(row, dict)
        ]

    return {
        "profit": body["profit"],
        "net_assets": body["net_assets"],
        "watermark": body["watermark"],
        "income": rows("income"),
        "sofp": rows("sofp"),
    }


@pytest.mark.asyncio
async def test_report_setup_does_not_change_stored_figures_or_rebuild(
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
    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    figures = _figures(before.json())
    assert figures["net_assets"] == "18400.40"
    anchor = _snapshot(org_id, year_end_id)
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    row_version = draft.json()["row_version"]

    def _refuse_rebuild(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("statement rebuild was called")

    original_build = statutory_statements.statements_for_adopted
    original_route = year_end_router.statements_for_adopted
    monkeypatch.setattr(
        "app.services.statutory_statements.statements_for_adopted",
        _refuse_rebuild,
    )
    monkeypatch.setattr(
        "app.routers.year_ends.statements_for_adopted",
        _refuse_rebuild,
    )
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "thousands",
            "statement_type": "compilation",
            "face_dates": {
                "current_start": "2024-04-01",
                "current_end": "2025-03-31",
                "prior_start": "2023-04-01",
                "prior_end": "2024-03-31",
            },
            "column_headers": {
                "as_at_current": "as at 31 March 2025",
                "as_at_prior": "as at 31 March 2024",
                "ended_current": "year ended 31 March 2025",
                "ended_prior": "year ended 31 March 2024",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["rounding"] == "thousands"
    assert body["statement_type"] == "compilation"
    assert body["face_dates"]["current_end"] == "2025-03-31"
    assert body["column_headers"]["ended_current"] == "year ended 31 March 2025"
    assert body["trial_balance_period_start"] == "2026-01-01"
    assert body["trial_balance_period_end"] == "2026-12-31"
    assert body["basis_id"] == "frs102-1a-ie"
    monkeypatch.setattr(
        "app.services.statutory_statements.statements_for_adopted",
        original_build,
    )
    monkeypatch.setattr(
        "app.routers.year_ends.statements_for_adopted",
        original_route,
    )

    after = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert after.status_code == 200, after.text
    assert _figures(after.json()) == figures
    assert _snapshot(org_id, year_end_id) == anchor
    again = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert again.json()["row_version"] == row_version

    refused = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "unit",
            "statement_type": "audit",
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
        },
    )
    assert refused.status_code == 422, refused.text
    review = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "unit",
            "statement_type": "review",
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
        },
    )
    assert review.status_code == 422, review.text
    still = await api_client.get(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
    )
    assert still.json()["statement_type"] == "compilation"
    assert still.json()["rounding"] == "thousands"
    assert _snapshot(org_id, year_end_id) == anchor


@pytest.mark.asyncio
async def test_framework_catalogue_is_not_a_single_frs_list(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    token = provisioned_org["token"]
    assert isinstance(token, str)
    listed = await api_client.get(
        "/year-ends/frameworks",
        headers=auth_headers(token),
    )
    assert listed.status_code == 200, listed.text
    frameworks = {item["id"]: item for item in listed.json()["frameworks"]}
    assert set(frameworks) == {"frs102-1a-ie", "form11-summary"}
    frs_labels = [section["label"] for section in frameworks["frs102-1a-ie"]["sections"]]
    form_labels = [section["label"] for section in frameworks["form11-summary"]["sections"]]
    assert frs_labels == [section.label for section in sections_for("frs102-1a-ie")]
    assert form_labels == [section.label for section in sections_for("form11-summary")]
    assert frameworks["frs102-1a-ie"]["available"] is True
    assert frameworks["form11-summary"]["available"] is False
    assert "Sub-line review" in frs_labels
    assert "Extracts summary" in form_labels
    assert "Extracts summary" not in frs_labels


def test_engine_sources_have_no_report_setup_import() -> None:
    for name in (
        "app/services/statutory_statements.py",
        "app/services/statutory_present.py",
        "app/services/draft_workflow.py",
    ):
        text = (_ROOT / name).read_text(encoding="utf-8")
        assert "report_setup" not in text
