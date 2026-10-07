"""Company letterhead and this year's approval. Figures stay the engine's."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.company_details import blocks_final
from app.services.draft_workflow import _can_finalise
from app.services.reconciliation import ReconciliationCheck
from tests.conftest import auth_headers
from tests.test_adopted_trial_balance import _CASH_PAIR, _insert_tb
from tests.test_findraft_tenant_isolation import (
    _as_app_role,
    _delete_org,
    _provision,
)
from tests.test_organisations_api import _add_org_user


@pytest.fixture
def two_practices() -> Iterator[tuple[dict, dict]]:
    suffix = uuid.uuid4().hex[:8]
    first = _provision(f"coa{suffix}")
    second = _provision(f"cob{suffix}")
    try:
        yield first, second
    finally:
        _delete_org(first["org_id"])
        _delete_org(second["org_id"])

_FORBIDDEN = "You don't have permission to access this resource."
_ARTIFACT = Path("/opt/cursor/artifacts/directors-report-pdf.txt")


def test_notices_do_not_block_final_and_missing_directors_do() -> None:
    notices = (
        ReconciliationCheck(
            "V-CO-003",
            "NOTICE",
            False,
            "The company secretary has not been recorded.",
        ),
        ReconciliationCheck(
            "V-CO-004",
            "NOTICE",
            False,
            "Principal activity has not been recorded.",
        ),
    )
    missing_directors = (
        ReconciliationCheck(
            "V-CO-001",
            "WARNING",
            False,
            "Directors have not been recorded.",
        ),
    )
    assert blocks_final(notices) is False
    assert (
        _can_finalise("amber", renderable=True, blocked=False, checks=notices) is True
    )
    assert blocks_final(missing_directors) is True
    assert (
        _can_finalise(
            "amber", renderable=True, blocked=False, checks=missing_directors
        )
        is False
    )


def _checks(body: dict[str, object]) -> dict[str, dict[str, object]]:
    rows = body["checks"]
    assert isinstance(rows, list)
    return {str(row["code"]): row for row in rows}


def _page(body: dict[str, object], heading: str) -> str:
    pages = body["pages"]
    assert isinstance(pages, list)
    match = next(page for page in pages if page["heading"] == heading)
    return "\n".join(match["paragraphs"])


def _pdf_text(payload: bytes) -> str:
    exe = shutil.which("pdftotext")
    assert exe is not None, "pdftotext is not installed"
    with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
        handle.write(payload)
        handle.flush()
        completed = subprocess.run(
            [exe, "-layout", handle.name, "-"],
            check=True,
            capture_output=True,
        )
    return completed.stdout.decode("utf-8")


def _audit_actions(org_id: uuid.UUID) -> set[str]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        rows = session.execute(
            text(
                "SELECT action FROM audit_logs WHERE org_id = :org "
                "AND action IN ('company_details_saved', 'year_end_approval_saved')"
            ),
            {"org": str(org_id)},
        ).scalars()
        return set(rows.all())


@pytest.mark.asyncio
async def test_saved_company_details_print_on_the_existing_pages(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Members save the letterhead. The directors' report and approval use it."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text("UPDATE companies SET industry = 'Bakeries' WHERE id = :id"),
            {"id": str(company_id)},
        )
        session.commit()
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=_CASH_PAIR,
        period_start=date(2026, 1, 1),
    )
    headers = auth_headers(provisioned_org["token"])
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
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft.json()['draft_id']}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    before_checks = _checks(board.json())
    assert before_checks["V-CO-001"]["passed"] is False
    assert before_checks["V-CO-001"]["message"] == "Directors have not been recorded."
    assert before_checks["V-CO-002"]["passed"] is False
    assert before_checks["V-CO-005"]["passed"] is False
    assert before_checks["V-CO-005"]["message"] == "Approval date has not been recorded."
    assert before_checks["V-CO-006"]["passed"] is False
    assert before_checks["V-CO-003"]["severity"] == "NOTICE"
    assert before_checks["V-CO-003"]["passed"] is False
    assert before_checks["V-CO-004"]["severity"] == "NOTICE"
    assert before_checks["V-CO-004"]["passed"] is False
    assert board.json()["can_finalise"] is False

    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    before_body = before.json()
    profit = before_body["profit"]
    net_assets = before_body["net_assets"]
    assert "have not been recorded" in _page(before_body, "Directors' report")
    assert "Approval date has not been recorded." in _page(
        before_body, "Approval of the financial statements"
    )

    _user_id, _clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="company-viewer",
    )
    viewer = auth_headers(viewer_token)
    refused = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=viewer,
        json={"registered_office": "1 Harbour Street"},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN
    readable = await api_client.get(
        f"/year-ends/{year_end_id}/company-details",
        headers=viewer,
    )
    assert readable.status_code == 200, readable.text

    missing = await api_client.get(
        f"/year-ends/{uuid.uuid4()}/company-details",
        headers=headers,
    )
    assert missing.status_code == 404, missing.text

    bad_number = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={"company_number": "12/345"},
    )
    assert bad_number.status_code == 400, bad_number.text
    assert bad_number.json()["detail"] == (
        "Company number must be letters and numbers, up to 20 characters."
    )
    early_resign = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={
            "directors": [
                {
                    "name": "Ada Lovelace",
                    "appointed_on": "2024-06-30",
                    "resigned_on": "2020-03-01",
                }
            ]
        },
    )
    assert early_resign.status_code == 400, early_resign.text
    assert early_resign.json()["detail"] == (
        "Resigned date is before the appointed date."
    )
    stranger = await api_client.put(
        f"/year-ends/{year_end_id}/approval",
        headers=headers,
        json={"signing_directors": ["Grace Hopper"]},
    )
    assert stranger.status_code == 400, stranger.text
    assert stranger.json()["detail"] == (
        "Signing director 'Grace Hopper' is not one of the directors on the company."
    )

    saved = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={
            "registered_office": "1 Harbour Street, Dublin",
            "business_address": "Unit 2\nDock Road",
            "company_number": "AB 123456",
            "incorporated_on": "2018-03-14",
            "principal_activity": "Software publishing",
            "secretary": "Grace Hopper",
            "directors": [
                {
                    "name": "Ada Lovelace",
                    "appointed_on": "2020-03-01",
                    "resigned_on": None,
                }
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    letterhead = saved.json()
    assert letterhead["registered_office"] == "1 Harbour Street, Dublin"
    assert letterhead["business_address"] == "Unit 2\nDock Road"
    assert letterhead["company_number"] == "AB123456"
    assert letterhead["incorporated_on"] == "2018-03-14"
    assert letterhead["principal_activity"] == "Software publishing"
    assert letterhead["secretary"] == "Grace Hopper"
    assert letterhead["directors"] == [
        {
            "name": "Ada Lovelace",
            "appointed_on": "2020-03-01",
            "resigned_on": None,
        }
    ]
    approved = await api_client.put(
        f"/year-ends/{year_end_id}/approval",
        headers=headers,
        json={
            "approval_date": "2027-03-15",
            "signing_directors": ["Ada Lovelace"],
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_date"] == "2027-03-15"
    assert approved.json()["signing_directors"] == ["Ada Lovelace"]
    assert _audit_actions(org_id) == {
        "company_details_saved",
        "year_end_approval_saved",
    }
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        industry = session.execute(
            text("SELECT industry FROM companies WHERE id = :id"),
            {"id": str(company_id)},
        ).scalar_one()
    assert industry == "Bakeries"

    after = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert after.status_code == 200, after.text
    after_body = after.json()
    assert after_body["profit"] == profit
    assert after_body["net_assets"] == net_assets
    directors = _page(after_body, "Directors' report")
    approval = _page(after_body, "Approval of the financial statements")
    assert (
        "The directors who served during the year are "
        "Ada Lovelace (appointed 2020-03-01)."
    ) in directors
    assert "The company secretary is Grace Hopper." in directors
    assert "Principal activities: Software publishing." in directors
    assert "Bakeries" not in directors
    assert "have not been recorded" not in directors
    assert "The financial statements were approved on 2027-03-15." in approval
    assert "The financial statements were signed by Ada Lovelace." in approval
    assert "not been recorded" not in approval
    assert "not been separately recorded" not in approval

    pdf = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements.pdf",
        headers=headers,
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    extracted = _pdf_text(pdf.content)
    for sentence in (
        "Ada Lovelace (appointed 2020-03-01)",
        "The company secretary is Grace Hopper.",
        "Principal activities: Software publishing.",
        "The financial statements were approved on 2027-03-15.",
        "The financial statements were signed by Ada Lovelace.",
    ):
        assert sentence in extracted, sentence
    assert "Bakeries" not in extracted
    assert "Principal activities have not been recorded." not in extracted
    assert "Approval date has not been recorded." not in extracted
    if _ARTIFACT.parent.is_dir():
        _ARTIFACT.write_text(
            "Directors' report\n"
            f"{directors}\n\n"
            "Approval of the financial statements\n"
            f"{approval}\n\n"
            "PDF text\n"
            f"{extracted}\n"
        )

    later = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft.json()['draft_id']}/dashboard",
        headers=headers,
    )
    assert later.status_code == 200, later.text
    filled = _checks(later.json())
    for code in ("V-CO-001", "V-CO-002", "V-CO-003", "V-CO-004", "V-CO-005", "V-CO-006"):
        assert filled[code]["passed"] is True, filled[code]
    assert later.json()["can_finalise"] is False


def test_new_columns_stay_inside_the_practice(
    two_practices: tuple[dict, dict],
) -> None:
    """Each new column is readable only inside the practice that owns the row."""
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            session.execute(text("RESET ROLE"))
            set_rls_org_id(session, first["org_id"])
            session.execute(
                text(
                    """
                    UPDATE companies
                    SET business_address = '1 Harbour Street',
                        incorporated_on = DATE '2018-03-14',
                        principal_activity = 'Software publishing'
                    WHERE id = :id
                    """
                ),
                {"id": str(first["company_id"])},
            )
            session.execute(
                text(
                    """
                    UPDATE findraft_year_ends
                    SET approval_date = DATE '2027-03-15',
                        signing_directors = CAST(:names AS jsonb)
                    WHERE id = :id
                    """
                ),
                {
                    "id": str(first["year_end_id"]),
                    "names": '["Ada Lovelace"]',
                },
            )
            session.flush()
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            own = session.execute(
                text(
                    """
                    SELECT business_address, incorporated_on::text, principal_activity
                    FROM companies
                    WHERE id = :id
                    """
                ),
                {"id": str(first["company_id"])},
            ).one()
            approval = session.execute(
                text(
                    """
                    SELECT approval_date::text, signing_directors
                    FROM findraft_year_ends
                    WHERE id = :id
                    """
                ),
                {"id": str(first["year_end_id"])},
            ).one()
            print(
                "columns=business_address,incorporated_on,principal_activity,"
                "approval_date,signing_directors",
                flush=True,
            )
            assert own.business_address == "1 Harbour Street"
            assert own.incorporated_on == "2018-03-14"
            assert own.principal_activity == "Software publishing"
            assert approval.approval_date == "2027-03-15"
            assert approval.signing_directors == ["Ada Lovelace"]
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(second["org_id"])},
            )
            hidden_company = session.execute(
                text(
                    """
                    SELECT business_address, incorporated_on, principal_activity
                    FROM companies
                    WHERE id = :id
                    """
                ),
                {"id": str(first["company_id"])},
            ).one_or_none()
            hidden_year = session.execute(
                text(
                    """
                    SELECT approval_date, signing_directors
                    FROM findraft_year_ends
                    WHERE id = :id
                    """
                ),
                {"id": str(first["year_end_id"])},
            ).one_or_none()
            assert hidden_company is None
            assert hidden_year is None
            leaked = session.execute(
                text(
                    """
                    SELECT business_address FROM companies
                    UNION ALL
                    SELECT principal_activity FROM companies
                    """
                )
            ).scalars().all()
            assert "1 Harbour Street" not in leaked
            assert "Software publishing" not in leaked
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))
