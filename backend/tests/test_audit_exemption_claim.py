"""Audit exemption claim for the fictional first-period company."""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.company_details import audit_position_checks, blocks_final
from app.services.statutory_compose import compose_pdf_html, compose_pdf_parts
from app.services.statutory_docx import build_docx
from app.services.statutory_pages import (
    audit_exemption_note,
    audit_exemption_statements,
)
from findraft.engine.pack import load_manifest, pack_dir
from findraft.models.year_end import YearEnd
from tests.conftest import auth_headers, make_access_token
from tests.test_adopted_trial_balance import _insert_tb, _set_file_hash
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_small_adopted_finalise import _ADMIN, _SMALL, _set_statutory
from tests.test_statutory_statements import _golden

_FORBIDDEN = "You don't have permission to access this resource."
_STATEMENT_MARK = (
    "(a) the company is availing itself of the exemption provided for by "
    "Chapter 15 of Part 6 of the Companies Act 2014,"
)
_NOTE = (
    "This page is an explanatory note. The audit exemption statement is "
    "printed on the balance sheet, immediately above the directors' "
    "signatures, as section 335 of the Companies Act 2014 requires."
)
_NOTE_HTML = _NOTE.replace("'", "&#39;")
_OLD_SENTENCE = "The directors are availing of the exemption from audit."
_NOT_RECORDED = (
    "The audit position has not been recorded. "
    "Record whether the audit exemption is claimed."
)
_REQUIRED = "An audit is required. An auditor's report is out of scope."
_SIZE_MISSING = (
    "The size test has not been recorded. "
    "Record it before the audit exemption can be evidenced."
)
_NOT_EVIDENCED = (
    "The recorded size test does not evidence the audit exemption. "
    "An audit is required. An auditor's report is out of scope."
)
_CLAIMED = "The audit exemption is claimed and the size test is recorded."
_SIZE_MESSAGE = (
    "Current year: turnover met; balance sheet total met; employees not met. "
    "This year end is a first financial period, so there is no preceding year. "
    "A reviewer must confirm whether the audit exemption is available "
    "(two of three versus all conditions)."
)
_CURRENT = {
    "turnover": "100000.00",
    "balance_sheet_total": "35000.00",
    "employees": 677,
}


def _year(**overrides: object) -> YearEnd:
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "period_start": datetime(2026, 1, 1, tzinfo=UTC).date(),
        "period_end": datetime(2026, 12, 31, tzinfo=UTC).date(),
        "first_financial_period": True,
        "pack_id": "frs102-1a-ie",
        "pack_version": "2024.09",
        "size_current_turnover": Decimal("100000.00"),
        "size_current_balance_sheet": Decimal("35000.00"),
        "size_current_employees": 677,
    }
    values.update(overrides)
    return YearEnd(**values)  # type: ignore[arg-type]


def _messages(year_end: YearEnd) -> dict[str, str]:
    return {item.code: item.message for item in audit_position_checks(year_end)}


def test_pack_statement_is_researched_from_the_cro_page() -> None:
    manifest = load_manifest(pack_dir("frs102-1a-ie", "2024.09") / "pack.json")
    assert set(manifest["thresholds"]) == {
        "regime",
        "currency",
        "rule",
        "years",
        "turnover",
        "balance_sheet",
        "employees",
    }
    block = manifest["audit_exemption_statements"]
    assert isinstance(block, dict)
    assert block["source"] == "CRO"
    assert block["provision"] == "Companies Act 2014, section 335"
    assert block["source_status"] == "researched (public source)"
    assert "confirmed" not in str(block["source_status"])
    assert "signed off" not in str(block["source_status"])
    paragraphs = audit_exemption_statements(manifest)
    assert paragraphs[1] == _STATEMENT_MARK
    assert "company\u2019s obligations" in paragraphs[4]
    assert "sections (a) \u2013 (d)" in paragraphs[7]
    assert audit_exemption_note(manifest) == _NOTE
    assert "eligible" not in " ".join(paragraphs).casefold()
    assert "confirmed" not in _NOTE.casefold()
    assert "signed off" not in _NOTE.casefold()


def test_each_claim_state_on_the_fictional_company() -> None:
    """677 employees, turnover 100,000, balance sheet 35,000, first period."""
    missing = _year()
    assert _messages(missing) == {"V-CO-020": _NOT_RECORDED}
    assert blocks_final(audit_position_checks(missing)) is True

    refused = _year(audit_exemption_claimed=False)
    assert _messages(refused) == {"V-CO-020": _REQUIRED}
    assert blocks_final(audit_position_checks(refused)) is True

    untested = _year(audit_exemption_claimed=True)
    assert _messages(untested) == {"V-CO-020": _SIZE_MISSING}
    assert blocks_final(audit_position_checks(untested)) is True

    failed = _year(
        audit_exemption_claimed=True,
        size_checked_at=datetime(2026, 10, 1, tzinfo=UTC),
        size_eligible=False,
        size_current_met=1,
        size_message="Current year: turnover not met; balance sheet total not met; employees not met.",
    )
    assert _messages(failed) == {"V-CO-020": _NOT_EVIDENCED}
    assert blocks_final(audit_position_checks(failed)) is True
    assert "eligible" not in _NOT_EVIDENCED.casefold()

    partial = _year(
        audit_exemption_claimed=True,
        size_checked_at=datetime(2026, 10, 1, tzinfo=UTC),
        size_eligible=True,
        size_current_met=2,
        size_message=_SIZE_MESSAGE,
    )
    found = {item.code: item for item in audit_position_checks(partial)}
    assert found["V-CO-020"].passed is True
    assert found["V-CO-020"].message == _CLAIMED
    assert found["V-CO-021"].passed is False
    assert found["V-CO-021"].severity == "NOTICE"
    assert found["V-CO-021"].message == _SIZE_MESSAGE
    assert "eligible" not in found["V-CO-021"].message.casefold()
    assert blocks_final(audit_position_checks(partial)) is False

    met = _year(
        audit_exemption_claimed=True,
        size_checked_at=datetime(2026, 10, 1, tzinfo=UTC),
        size_eligible=True,
        size_current_met=3,
        size_message="Current year: turnover met; balance sheet total met; employees met.",
    )
    assert _messages(met) == {"V-CO-020": _CLAIMED}
    assert blocks_final(audit_position_checks(met)) is False


def test_cro_statement_prints_on_the_balance_sheet_above_the_signatures(
    tmp_path: Path,
) -> None:
    plain = _golden()
    assert plain.html is not None
    assert plain.net_assets == Decimal("455812.00")
    assert plain.profit == Decimal("157650.00")
    assert _STATEMENT_MARK not in plain.html
    assert _NOTE not in plain.html
    assert "source not confirmed" not in plain.html

    claimed = _golden(audit_exemption_claimed=True)
    assert claimed.net_assets == plain.net_assets
    assert claimed.profit == plain.profit
    statements = audit_exemption_statements(
        load_manifest(pack_dir("frs102-1a-ie", "2024.09") / "pack.json")
    )
    assert claimed.audit_exemption_statements == statements
    assert claimed.html is not None
    audit = claimed.html.split('data-section="audit-exemption"', 1)[1]
    audit_body = audit.split('data-section="', 1)[0]
    sofp = claimed.html.split('data-section="sofp"', 1)[1]
    before_signature, _signature = sofp.split('<section class="signature">', 1)
    assert _NOTE_HTML in audit_body
    assert _STATEMENT_MARK not in audit_body
    assert _OLD_SENTENCE not in claimed.html
    assert _STATEMENT_MARK in before_signature
    assert "company\u2019s obligations" in before_signature
    assert _STATEMENT_MARK not in _signature
    assert "source not confirmed" not in claimed.html

    refused = _golden(audit_exemption_claimed=False)
    assert refused.html is not None
    assert _STATEMENT_MARK not in refused.html
    assert _NOTE not in refused.html
    assert "does not claim the audit exemption" in refused.html

    composed = compose_pdf_html(
        claimed,
        report_setup=None,
        period_start=datetime(2025, 1, 1, tzinfo=UTC).date(),
        period_end=datetime(2025, 12, 31, tzinfo=UTC).date(),
        first_financial_period=False,
    )
    composed_audit = composed.split('data-section="audit-exemption"', 1)[1]
    composed_sofp = composed.split('data-section="sofp"', 1)[1]
    composed_before, _composed_signature = composed_sofp.split(
        '<section class="signature">', 1
    )
    assert _NOTE_HTML in composed_audit.split("</section>", 1)[0]
    assert _STATEMENT_MARK not in composed_audit.split("</section>", 1)[0]
    assert _STATEMENT_MARK in composed_before
    assert "source not confirmed" not in composed
    _html, sections = compose_pdf_parts(
        claimed,
        report_setup=None,
        period_start=datetime(2025, 1, 1, tzinfo=UTC).date(),
        period_end=datetime(2025, 12, 31, tzinfo=UTC).date(),
        first_financial_period=False,
    )
    balance = next(section for section in sections if section.get("anchor") == "sofp")
    assert balance["exemption_statements"] == list(statements)
    dest = tmp_path / "claimed.docx"
    build_docx(
        {
            "watermark": "DRAFT",
            "company_name": "charlie mungar buffett",
            "page_header": "DRAFT",
            "composed": sections,
        },
        dest,
    )
    xml = zipfile.ZipFile(BytesIO(dest.read_bytes())).read("word/document.xml").decode()
    assert xml.count(_STATEMENT_MARK) == 1
    assert xml.count(_NOTE) == 1


def _headers(
    provisioned_org: dict, *, role: str, prefix: str
) -> tuple[dict[str, str], uuid.UUID]:
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role=role,
        email_prefix=prefix,
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role=role)
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role=role,
        org_uuid=provisioned_org["org_id"],
    )
    return auth_headers(token), user_id


async def _open_fixture(
    api_client: AsyncClient, provisioned_org: dict
) -> tuple[str, str, dict[str, str]]:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE companies SET name = :name, functional_currency = 'EUR' "
                "WHERE id = :id"
            ),
            {"name": "charlie mungar buffett", "id": str(company_id)},
        )
        session.execute(
            text("UPDATE organisations SET name = :name WHERE id = :id"),
            {"name": "kastree's Organization", "id": str(org_id)},
        )
        session.commit()
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=_SMALL,
        period_start=datetime(2026, 1, 1, tzinfo=UTC).date(),
    )
    _set_file_hash(tb_id, org_id, "ab" * 32)
    _set_statutory(org_id=org_id, company_id=company_id, lines=_ADMIN)
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={
            "registered_office": "New York, Ireland",
            "company_number": "1111",
            "incorporated_on": "2025-05-07",
            "secretary": "Warren Buffet",
            "average_employees": 677,
            "directors": [
                {"name": "warren buffett", "appointed_on": "2025-07-03"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    return year_end_id, draft.json()["draft_id"], headers


def _check(body: dict[str, object], code: str) -> dict[str, object]:
    checks = body["checks"]
    assert isinstance(checks, list)
    return next(
        item for item in checks if isinstance(item, dict) and item["code"] == code
    )


async def _dashboard(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    draft_id: str,
) -> dict[str, object]:
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    body = board.json()
    assert isinstance(body, dict)
    return body


async def _preview(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    section: str,
) -> str:
    shown = await api_client.get(
        f"/year-ends/{year_end_id}/statutory-preview",
        headers=headers,
        params={"section": section},
    )
    assert shown.status_code == 200, shown.text
    html = shown.json()["html"]
    assert isinstance(html, str)
    return html


@pytest.mark.asyncio
async def test_fictional_company_claim_is_owner_admin_only_and_prints_when_true(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id, draft_id, owner = await _open_fixture(api_client, provisioned_org)
    member, _member_id = _headers(provisioned_org, role="member", prefix="claim-member")
    viewer, _viewer_id = _headers(provisioned_org, role="viewer", prefix="claim-viewer")
    admin, admin_id = _headers(provisioned_org, role="admin", prefix="claim-admin")

    stored = await api_client.get(f"/year-ends/{year_end_id}", headers=owner)
    assert stored.status_code == 200, stored.text
    assert stored.json()["audit_exemption_claimed"] is None
    assert stored.json()["audit_exemption_claimed_by_user_id"] is None
    assert stored.json()["audit_exemption_claimed_at"] is None
    board = await _dashboard(api_client, owner, year_end_id, draft_id)
    assert _check(board, "V-CO-020")["message"] == _NOT_RECORDED
    assert _check(board, "V-CO-020")["passed"] is False
    assert isinstance(board["checks"], list)
    assert "V-CO-021" not in [item["code"] for item in board["checks"]]
    before = await _preview(api_client, owner, year_end_id, "audit-exemption")
    balance = await _preview(api_client, owner, year_end_id, "sofp")
    assert _STATEMENT_MARK not in before
    assert _STATEMENT_MARK not in balance
    assert _NOTE not in before
    assert "The size test has not been recorded." in before
    assert "source not confirmed" not in before

    for headers in (member, viewer):
        refused = await api_client.post(
            f"/year-ends/{year_end_id}/audit-exemption",
            headers=headers,
            json={"claimed": True},
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["detail"] == _FORBIDDEN

    claimed = await api_client.post(
        f"/year-ends/{year_end_id}/audit-exemption",
        headers=admin,
        json={"claimed": True},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["claimed"] is True
    assert claimed.json()["claimed_by_user_id"] == str(admin_id)
    waiting = await _dashboard(api_client, owner, year_end_id, draft_id)
    assert _check(waiting, "V-CO-020")["message"] == _SIZE_MISSING
    assert _check(waiting, "V-CO-020")["passed"] is False
    early_audit = await _preview(api_client, owner, year_end_id, "audit-exemption")
    early_balance = await _preview(api_client, owner, year_end_id, "sofp")
    assert _NOTE_HTML in early_audit
    assert _STATEMENT_MARK not in early_audit
    assert _STATEMENT_MARK in early_balance

    recorded = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=member,
        json={"current": _CURRENT},
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["message"] == _SIZE_MESSAGE
    evidenced = await _dashboard(api_client, owner, year_end_id, draft_id)
    assert _check(evidenced, "V-CO-020")["passed"] is True
    assert _check(evidenced, "V-CO-020")["message"] == _CLAIMED
    notice = _check(evidenced, "V-CO-021")
    assert notice["passed"] is False
    assert notice["message"] == _SIZE_MESSAGE
    assert "eligible" not in str(notice["message"]).casefold()
    fix = notice["fix"]
    assert isinstance(fix, dict)
    assert fix["section"] == "review"
    audit_page = await _preview(api_client, owner, year_end_id, "audit-exemption")
    balance = await _preview(api_client, owner, year_end_id, "sofp")
    assert _NOTE_HTML in audit_page
    assert _STATEMENT_MARK not in audit_page
    assert _STATEMENT_MARK in balance
    assert "source not confirmed" not in audit_page
    assert "source not confirmed" not in balance
    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=owner,
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["profit"] == "25000.00"
    assert statements.json()["net_assets"] == "35000.00"
    page = next(
        item
        for item in statements.json()["pages"]
        if item["heading"] == "Audit exemption"
    )
    assert page["paragraphs"] == [_NOTE]

    not_claimed = await api_client.post(
        f"/year-ends/{year_end_id}/audit-exemption",
        headers=owner,
        json={"claimed": False},
    )
    assert not_claimed.status_code == 200, not_claimed.text
    assert not_claimed.json()["claimed"] is False
    assert not_claimed.json()["claimed_by_user_id"] == str(provisioned_org["user_id"])
    required = await _dashboard(api_client, owner, year_end_id, draft_id)
    assert _check(required, "V-CO-020")["message"] == _REQUIRED
    assert _check(required, "V-CO-020")["passed"] is False
    hidden = await _preview(api_client, owner, year_end_id, "sofp")
    audit_page = await _preview(api_client, owner, year_end_id, "audit-exemption")
    assert _STATEMENT_MARK not in hidden
    assert _STATEMENT_MARK not in audit_page
    assert _NOTE not in audit_page
    assert "does not make the statement required by section 335" in audit_page
    assert "have not recorded that they are availing" in audit_page

    cleared = await api_client.post(
        f"/year-ends/{year_end_id}/audit-exemption",
        headers=owner,
        json={"claimed": None},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["claimed"] is None
    assert cleared.json()["claimed_by_user_id"] is None
    assert cleared.json()["claimed_at"] is None
    blank = await _dashboard(api_client, owner, year_end_id, draft_id)
    assert _check(blank, "V-CO-020")["message"] == _NOT_RECORDED
    year_end = await api_client.get(f"/year-ends/{year_end_id}", headers=viewer)
    assert year_end.status_code == 200, year_end.text
    assert year_end.json()["audit_exemption_claimed"] is None

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        rows = session.execute(
            text(
                """
                SELECT user_id, old_value, new_value
                FROM audit_logs
                WHERE org_id = :org AND action = 'audit_exemption_claimed'
                ORDER BY chain_seq
                """
            ),
            {"org": str(provisioned_org["org_id"])},
        ).all()
    assert len(rows) == 3
    assert rows[0].old_value is None
    assert rows[0].user_id == admin_id
    assert rows[0].new_value["claimed"] is True
    assert rows[0].new_value["claimed_by_user_id"] == str(admin_id)
    assert rows[1].old_value["claimed"] is True
    assert rows[1].user_id == provisioned_org["user_id"]
    assert rows[1].new_value["claimed"] is False
    assert rows[2].old_value["claimed"] is False
    assert rows[2].new_value == {
        "claimed": None,
        "claimed_by_user_id": None,
        "claimed_at": None,
    }
    logged = json.dumps(
        [row.old_value for row in rows] + [row.new_value for row in rows]
    )
    for row in rows:
        assert set(row.new_value) == {
            "claimed",
            "claimed_by_user_id",
            "claimed_at",
        }
    assert "100000" not in logged
    assert "35000" not in logged
    assert "677" not in logged
    assert "turnover" not in logged
    assert "balance_sheet" not in logged
