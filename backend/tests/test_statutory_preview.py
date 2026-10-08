"""Section preview is a slice of the PDF HTML."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.services.statutory_compose import (
    PREVIEW_CONTENT_SECURITY_POLICY,
    children_of,
    compose_pdf_parts,
    extract_section_html,
    preview_document,
)
from app.services.statutory_preview import NOT_RENDERABLE, SECTION_ABSENT
from tests.conftest import auth_headers, make_access_token
from tests.test_adopted_trial_balance import _insert_tb
from tests.test_findraft_tenant_isolation import _delete_org, _provision
from tests.test_organisations_api import _add_org_user
from tests.test_statutory_statements import _golden

_FORBIDDEN = "You don't have permission to access this resource."


def _setup() -> dict[str, object]:
    return {
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


def test_preview_section_matches_the_pdf_source_and_note_number() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    html, sections = compose_pdf_parts(
        document,
        report_setup=_setup(),
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
    )
    for anchor in ("cover", "contents", "income", "sofp", "notes"):
        section = extract_section_html(html, anchor)
        assert section is not None
        assert section in html
        shell = preview_document(html, section)
        assert extract_section_html(shell, anchor) == section
        assert "default-src 'none'" in shell
    debtors = next(
        child for child in children_of(sections, "notes") if child.id == "N3_DEBTORS"
    )
    heading = f"{debtors.number}. {debtors.label}"
    notes = extract_section_html(html, "notes")
    assert notes is not None
    assert f'<h3 class="note-title">{heading}</h3>' in notes
    assert f'id="{debtors.anchor}"' in notes
    assert [child.id for child in children_of(sections, "compilation")] == [
        "approval",
        "audit-exemption",
    ]
    hidden = compose_pdf_parts(
        document,
        report_setup={**_setup(), "sections": {"directors-report": False}},
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        first_financial_period=False,
    )[0]
    assert extract_section_html(hidden, "directors-report") is None
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")


async def _open_renderable_year_end(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> tuple[str, str]:
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
    return year_end_id, str(tb_id)


@pytest.mark.asyncio
async def test_preview_route_matches_pdf_html_and_hides_a_disabled_section(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    year_end_id, _tb_id = await _open_renderable_year_end(api_client, provisioned_org)
    headers = auth_headers(str(provisioned_org["token"]))
    preview = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "income"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-security-policy"] == PREVIEW_CONTENT_SECURITY_POLICY
    assert preview.headers["cache-control"] == "private, must-revalidate"
    assert preview.headers["etag"] == f'"{preview.json()["preview_revision"]}"'
    body = preview.json()
    section = extract_section_html(body["html"], "income")
    assert section is not None
    captured: list[str] = []

    def _capture(html: str) -> bytes:
        captured.append(html)
        return b"%PDF-1.7 captured"

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("app.routers.year_ends.write_statement_pdf", _capture)
    pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    monkeypatch.undo()
    assert pdf.status_code == 200, pdf.text
    assert section == extract_section_html(captured[0], "income")
    notes = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "notes"},
    )
    assert notes.status_code == 200, notes.text
    printed = next(
        child for child in notes.json()["children"] if child["id"] == "N0_ENTITY"
    )
    notes_html = extract_section_html(notes.json()["html"], "notes")
    assert notes_html is not None
    assert (
        f'<h3 class="note-title">{printed["number"]}. {printed["label"]}</h3>'
        in notes_html
    )
    hidden = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
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
            "sections": {"directors-report": False},
        },
    )
    assert hidden.status_code == 200, hidden.text
    absent = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "directors-report"},
    )
    assert absent.status_code == 404, absent.text
    assert absent.json()["detail"] == SECTION_ABSENT


@pytest.mark.asyncio
async def test_product1_remap_and_git_sha_change_the_preview_revision(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id, _tb_id = await _open_renderable_year_end(api_client, provisioned_org)
    headers = auth_headers(str(provisioned_org["token"]))
    first = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "sofp"},
    )
    assert first.status_code == 200, first.text
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        mapping = session.scalar(
            select(AccountMapping).where(
                AccountMapping.company_id == company_id,
                AccountMapping.source_code == "2130",
            )
        )
        assert mapping is not None
        assert mapping.canonical_line == "cash"
        mapping.canonical_line = "trade_receivables"
        session.commit()
    remapped = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "sofp"},
    )
    assert remapped.status_code == 200, remapped.text
    assert remapped.json()["preview_revision"] != first.json()["preview_revision"]
    assert remapped.json()["row_version"] == first.json()["row_version"]
    monkeypatch.setattr(settings, "git_sha", "preview-revision-probe")
    moved = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "sofp"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["preview_revision"] != remapped.json()["preview_revision"]


@pytest.mark.asyncio
async def test_preview_is_readable_by_a_viewer_and_hidden_from_another_practice(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    year_end_id, _tb_id = await _open_renderable_year_end(api_client, provisioned_org)
    org_id = provisioned_org["org_id"]
    clerk_org_id = provisioned_org["clerk_org_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(clerk_org_id, str)
    _user_id, _clerk_user_id, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=clerk_org_id,
        role="viewer",
        email_prefix="preview-viewer",
    )
    viewer = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=auth_headers(viewer_token),
        params={"section": "cover"},
    )
    assert viewer.status_code == 200, viewer.text
    suffix = uuid.uuid4().hex[:10]
    other = _provision(suffix)
    try:
        other_token = make_access_token(
            clerk_user_id=f"user_fd_{suffix}",
            clerk_org_id=f"org_fd_{suffix}",
            org_uuid=other["org_id"],
        )
        hidden = await api_client.get(
            f"/year-ends/{year_end_id}/statutory-preview",
            headers=auth_headers(other_token),
            params={"section": "cover"},
        )
        assert hidden.status_code == 404, hidden.text
        assert hidden.json()["detail"] == "Year end not found"
    finally:
        _delete_org(other["org_id"])


@pytest.mark.asyncio
async def test_production_preview_rejects_a_non_admin(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_emails", "founder-only@example.com")
    response = await api_client.get(
        f"/year-ends/{uuid.uuid4()}/statutory-preview",
        headers=auth_headers(str(provisioned_org["token"])),
        params={"section": "income"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == _FORBIDDEN


@pytest.mark.asyncio
async def test_unrenderable_preview_uses_the_pdf_message(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
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
            ("2130", "Bank current account", "10.00", "0.00", "10.00", "cash"),
            ("3000", "Called up share capital", "0.00", "10.00", "-10.00", "share_capital"),
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
    blocked = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": "income"},
    )
    assert blocked.status_code == 400, blocked.text
    assert blocked.json()["detail"] == NOT_RENDERABLE
