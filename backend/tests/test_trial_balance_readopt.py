"""Confirmed re-adopt of a different trial balance. Parity runs this as findraft."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.prior_year_line import PriorYearLine
from app.models.trial_balance import TrialBalance
from app.services.org_provisioning import provision_first_signup
from app.services.trial_balance_readopt import (
    add_months,
    period_longer_than_18_months,
)
from tests.conftest import (
    _grant_append_only_delete,
    _revoke_append_only_delete,
    auth_headers,
    balanced_tb_xlsx_bytes,
    make_access_token,
)
from tests.test_adopted_trial_balance import _CASH_PAIR, _parsed_rows
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role

_LOCK = (
    "This statutory draft is final, locked, or frozen. The period cannot be changed."
)
_PACK = (
    "This pack applies to periods beginning on or after 1 January 2026. "
    "This trial balance starts on 31 December 2025."
)


def test_eighteen_months_is_a_block_at_the_anniversary() -> None:
    assert add_months(date(2026, 1, 1), 18) == date(2027, 7, 1)
    assert period_longer_than_18_months(date(2026, 1, 1), date(2027, 6, 30)) is False
    assert period_longer_than_18_months(date(2026, 1, 1), date(2027, 7, 1)) is True


def _insert_file(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    period_start: date | None,
    period_end: date,
    currency: str = "GBP",
    filename: str | None = "next.xlsx",
    rows: tuple[tuple[str, str, str, str, str, str], ...] = _CASH_PAIR,
    status: str = "complete",
) -> uuid.UUID:
    tb_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                company_id=company_id,
                period_end=period_end,
                period_start=period_start,
                file_url=f"file:///tmp/{tb_id}.csv",
                file_type="csv",
                status=status,
                currency=currency,
                original_filename=filename,
                parsed_data=_parsed_rows(
                    tuple(
                        (code, name, debit, credit, net)
                        for code, name, debit, credit, net, _line in rows
                    )
                ),
            )
        )
        for code, name, _debit, _credit, _net, line in rows:
            existing = session.scalar(
                select(AccountMapping.id).where(
                    AccountMapping.company_id == company_id,
                    AccountMapping.source_code == code,
                    AccountMapping.source_name == name,
                )
            )
            if existing is not None:
                continue
            session.add(
                AccountMapping(
                    company_id=company_id,
                    source_code=code,
                    source_name=name,
                    canonical_line=line,
                    confidence=Decimal("1.00"),
                    method="manual",
                    is_confirmed=True,
                    is_ignored=False,
                )
            )
        session.commit()
    return tb_id


async def _open(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> tuple[str, str, dict[str, str], uuid.UUID]:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    tb_id = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        filename="year-end.xlsx",
    )
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = str(opened.json()["year_end_id"])
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    return year_end_id, str(draft.json()["draft_id"]), headers, tb_id


def _year_end_row(year_end_id: str, org_id: uuid.UUID) -> dict[str, object]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = (
            session.execute(
                text(
                    """
                SELECT period_start::text AS period_start,
                       period_end::text AS period_end,
                       adopted_trial_balance_id::text AS adopted,
                       report_setup,
                       first_financial_period,
                       comparative_source_year_end_id::text AS source_year_end,
                       comparative_source_draft_id::text AS source_draft
                FROM findraft_year_ends
                WHERE id = :id
                """
                ),
                {"id": year_end_id},
            )
            .mappings()
            .one()
        )
    return dict(row)


def _draft_row(draft_id: str, org_id: uuid.UUID) -> dict[str, object]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = (
            session.execute(
                text(
                    """
                SELECT version_number, status, row_version, is_frozen,
                       adjustments_basis_trial_balance_id::text AS basis,
                       note_library
                FROM findraft_draft_versions
                WHERE id = :id
                """
                ),
                {"id": draft_id},
            )
            .mappings()
            .one()
        )
    return dict(row)


def _audit(org_id: uuid.UUID, action: str) -> list[tuple[object, object]]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        return list(
            session.execute(
                text(
                    """
                    SELECT old_value, new_value
                    FROM audit_logs
                    WHERE org_id = :org AND action = :action
                    """
                ),
                {"org": str(org_id), "action": action},
            ).all()
        )


def _journal_count(draft_id: str, org_id: uuid.UUID) -> int:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(
            text(
                """
                SELECT count(*) FROM findraft_adjustment_journals
                WHERE draft_version_id = :id
                """
            ),
            {"id": draft_id},
        ).scalar_one()
    return int(count)


def _set_draft(
    draft_id: str,
    org_id: uuid.UUID,
    *,
    status: str | None = None,
    frozen: bool | None = None,
    note_library: bool = False,
) -> None:
    assignments = ["updated_at = NOW()"]
    if status is not None:
        assignments.append("status = :status")
        if status == "final":
            assignments.append("snapshot = COALESCE(snapshot, '{\"kept\": true}'::jsonb)")
            assignments.append("inputs_sha256 = COALESCE(inputs_sha256, :sha)")
            assignments.append("engine_sha = COALESCE(engine_sha, :sha)")
    if frozen is not None:
        assignments.append("is_frozen = :frozen")
    if note_library:
        assignments.append("""note_library = '{"stored": true}'::jsonb""")
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                f"UPDATE findraft_draft_versions SET {', '.join(assignments)} WHERE id = :id"
            ),
            {
                "id": draft_id,
                "status": status,
                "frozen": frozen,
                "sha": "a" * 64,
            },
        )
        session.commit()


async def _post_journals(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    draft_id: str,
    row_version: int,
) -> int:
    first = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/adjustments",
        headers={**headers, "Idempotency-Key": f"readopt-present-{draft_id}"},
        json={
            "row_version": row_version,
            "narration": "Present accounts",
            "lines": [
                {
                    "nominal_code": "2130",
                    "account_name": "Bank current account",
                    "canonical_line": "CASH",
                    "debit": "10.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "3000",
                    "account_name": "Called up share capital",
                    "canonical_line": "SHARE_CAPITAL",
                    "debit": "0.00",
                    "credit": "10.00",
                },
            ],
        },
    )
    assert first.status_code == 200, first.text
    second = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/adjustments",
        headers={**headers, "Idempotency-Key": f"readopt-absent-{draft_id}"},
        json={
            "row_version": first.json()["row_version"],
            "narration": "Account missing from the new file",
            "lines": [
                {
                    "nominal_code": "7100",
                    "account_name": "Admin overhead",
                    "canonical_line": "ADMIN_EXPENSES",
                    "debit": "5.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "7200",
                    "account_name": "Sundry creditor",
                    "canonical_line": "OTHER_CREDITORS",
                    "debit": "0.00",
                    "credit": "5.00",
                },
            ],
        },
    )
    assert second.status_code == 200, second.text
    return int(second.json()["row_version"])


@pytest.mark.asyncio
async def test_preview_lists_journals_and_confirm_keeps_them(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    year_end_id, draft_id, headers, old_tb = await _open(api_client, provisioned_org)
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    row_version = await _post_journals(
        api_client, headers, year_end_id, draft_id, int(draft.json()["row_version"])
    )
    disclosed = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/disclosures",
        headers=headers,
        json={
            "row_version": row_version,
            "flag_name": "HAS_EMPLOYEES",
            "answer": "yes",
        },
    )
    assert disclosed.status_code == 200, disclosed.text
    row_version = int(disclosed.json()["row_version"])
    _set_draft(draft_id, org_id, note_library=True)
    new_tb = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 12, 31),
        filename="replaced.xlsx",
    )
    listed = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance/candidates",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    match = [row for row in listed.json()["items"] if row["id"] == str(new_tb)]
    assert len(match) == 1
    assert match[0]["file_name"] == "replaced.xlsx"
    assert match[0]["period_start"] == "2027-01-01"
    assert match[0]["ready"] is True
    assert match[0]["account_count"] == 2
    preview = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(new_tb),
            "row_version": row_version,
            "confirm": False,
        },
    )
    assert preview.status_code == 422, preview.text
    body = preview.json()
    assert body["draft_id"] == draft_id
    assert body["version_number"] == 1
    assert body["disclosure_answer_count"] == 1
    assert body["note_library_stored"] is True
    assert body["period_start"] == "2027-01-01"
    assert body["period_end"] == "2027-12-31"
    narrations = {row["narration"]: row for row in body["journals"]}
    assert set(narrations) == {"Present accounts", "Account missing from the new file"}
    present = {
        (line["nominal_code"], line["account_name"]): line["present"]
        for line in narrations["Present accounts"]["lines"]
    }
    assert present[("2130", "Bank current account")] is True
    assert present[("3000", "Called up share capital")] is True
    absent = narrations["Account missing from the new file"]["lines"]
    assert {line["present"] for line in absent} == {False}
    encoded = preview.text
    assert "10.00" not in encoded
    assert "5.00" not in encoded
    assert _audit(org_id, "trial_balance_readopted") == []
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)

    saved = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(new_tb),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["draft_id"] == draft_id
    assert saved.json()["version_number"] == 1
    assert saved.json()["trial_balance_id"] == str(new_tb)
    assert saved.json()["adjustments_notice"] == (
        "This draft's adjustments were made against a different trial balance"
    )
    stored = _year_end_row(year_end_id, org_id)
    assert stored["period_start"] == "2027-01-01"
    assert stored["period_end"] == "2027-12-31"
    assert stored["adopted"] == str(new_tb)
    draft_stored = _draft_row(draft_id, org_id)
    assert draft_stored["basis"] == str(old_tb)
    assert draft_stored["version_number"] == 1
    assert draft_stored["note_library"] == {"stored": True}
    assert _journal_count(draft_id, org_id) == 2
    audit = _audit(org_id, "trial_balance_readopted")
    assert len(audit) == 1
    old_value, new_value = audit[0]
    assert old_value["adopted_trial_balance_id"] == str(old_tb)
    assert new_value["draft_id"] == draft_id
    assert "draft_id" not in old_value
    assert "narration" not in str(audit)
    assert "replaced.xlsx" not in str(audit)
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    assert board.json()["adjustments_notice"] == (
        "This draft's adjustments were made against a different trial balance"
    )
    page = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance", headers=headers
    )
    assert page.json()["can_switch"] is True
    assert page.json()["file_name"] == "replaced.xlsx"
    assert page.json()["adjustments_notice"] == board.json()["adjustments_notice"]

    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=org_id,
        clerk_org_id=str(provisioned_org["clerk_org_id"]),
        role="member",
        email_prefix="readopt-viewer",
    )
    viewer_token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=str(provisioned_org["clerk_org_id"]),
        role="owner",
        org_uuid=org_id,
    )
    _set_role(org_id=org_id, user_id=user_id, role="viewer")
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adjustments-confirmed",
        headers=auth_headers(viewer_token),
        json={"row_version": saved.json()["row_version"]},
    )
    assert refused.status_code == 403, refused.text
    assert (
        refused.json()["detail"] == "You don't have permission to access this resource."
    )

    confirmed = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adjustments-confirmed",
        headers=headers,
        json={"row_version": saved.json()["row_version"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["adjustments_notice"] is None
    assert _draft_row(draft_id, org_id)["basis"] == str(new_tb)
    reconfirmed = _audit(org_id, "adjustments_reconfirmed")
    assert len(reconfirmed) == 1
    _old, new_audit = reconfirmed[0]
    assert new_audit["year_end_id"] == year_end_id
    assert new_audit["draft_id"] == draft_id
    assert new_audit["previous_trial_balance_id"] == str(old_tb)
    assert new_audit["current_trial_balance_id"] == str(new_tb)
    assert "narration" not in str(reconfirmed)
    cleared = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert cleared.json()["adjustments_notice"] is None


@pytest.mark.asyncio
async def test_same_file_and_stale_version_write_nothing(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, _draft_id, headers, tb_id = await _open(api_client, provisioned_org)
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    same = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(tb_id),
            "row_version": draft.json()["row_version"],
            "confirm": True,
        },
    )
    assert same.status_code == 422, same.text
    assert same.json()["detail"] == "This trial balance is already selected."
    assert _audit(org_id, "trial_balance_readopted") == []
    company_id = provisioned_org["company_id"]
    assert isinstance(company_id, uuid.UUID)
    other = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 12, 31),
        filename="stale.xlsx",
    )
    stale = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(other),
            "row_version": int(draft.json()["row_version"]) + 9,
            "confirm": True,
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"] == "row_version does not match"
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(tb_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["final", "locked"])
async def test_closed_drafts_refuse_a_period_change(
    api_client: AsyncClient, provisioned_org: dict[str, object], status: str
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    year_end_id, draft_id, headers, old_tb = await _open(api_client, provisioned_org)
    _set_draft(draft_id, org_id, status=status)
    new_tb = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 12, 31),
        filename=f"{status}.xlsx",
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={"trial_balance_id": str(new_tb), "row_version": 1, "confirm": True},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == _LOCK
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)
    page = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance", headers=headers
    )
    assert page.json()["can_switch"] is False
    assert page.json()["switch_refusal"] == _LOCK


@pytest.mark.asyncio
async def test_frozen_draft_refuses_a_period_change(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    year_end_id, draft_id, headers, old_tb = await _open(api_client, provisioned_org)
    _set_draft(draft_id, org_id, frozen=True)
    new_tb = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 12, 31),
    )
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={"trial_balance_id": str(new_tb), "row_version": 1, "confirm": False},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == _LOCK
    assert _year_end_row(year_end_id, org_id)["period_end"] == "2026-12-31"
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)


@pytest.mark.asyncio
async def test_pack_date_currency_and_contiguity_leave_the_year_end(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    year_end_id, _draft_id, headers, old_tb = await _open(api_client, provisioned_org)
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    row_version = int(draft.json()["row_version"])

    early = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2025, 12, 31),
        period_end=date(2026, 11, 30),
        filename="early.xlsx",
    )
    pack = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(early),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert pack.status_code == 422, pack.text
    assert pack.json()["detail"] == _PACK
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)

    foreign = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 9, 30),
        currency="USD",
        filename="usd.xlsx",
    )
    currency = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(foreign),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert currency.status_code == 422, currency.text
    assert currency.json()["detail"] == (
        "This trial balance is in USD. The company reports in GBP. Amounts are not converted."
    )
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)

    previous = await api_client.post(
        "/year-ends",
        headers=headers,
        json={
            "company_id": str(company_id),
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
        },
    )
    assert previous.status_code == 400, previous.text
    # The Irish pack refuses a 2025 start at creation. Insert the row for contiguity.
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_start, period_end, pack_id, pack_version
                )
                SELECT :id, org_id, company_id, '2025-01-01', '2025-12-31', pack_id, pack_version
                FROM findraft_year_ends
                WHERE id = :current
                """
            ),
            {"id": str(uuid.uuid4()), "current": year_end_id},
        )
        session.commit()
    gap = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2026, 1, 2),
        period_end=date(2027, 6, 30),
        filename="gap.xlsx",
    )
    # Same period end as the open year end is not a collision with another row.
    # The previous period ended 2025-12-31, so 2 January is not the next day.
    noncontiguous = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(gap),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert noncontiguous.status_code == 409, noncontiguous.text
    assert "2026-01-02" in noncontiguous.json()["detail"]
    assert "2025-12-31" in noncontiguous.json()["detail"]
    assert "2026-01-01" in noncontiguous.json()["detail"]
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                UPDATE findraft_year_ends
                SET first_financial_period = true
                WHERE id = :id
                """
            ),
            {"id": year_end_id},
        )
        session.commit()
    contiguous = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 30),
        filename="first.xlsx",
    )
    first_period = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(contiguous),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert first_period.status_code == 409, first_period.text
    assert "first financial period" in first_period.json()["detail"]
    assert "2025-12-31" in first_period.json()["detail"]
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                DELETE FROM findraft_year_ends
                WHERE org_id = :org AND period_end = '2025-12-31'
                """
            ),
            {"org": str(org_id)},
        )
        session.execute(
            text(
                """
                UPDATE findraft_year_ends
                SET first_financial_period = false
                WHERE id = :id
                """
            ),
            {"id": year_end_id},
        )
        following_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO findraft_year_ends (
                  id, org_id, company_id, period_start, period_end, pack_id, pack_version
                )
                SELECT :id, org_id, company_id, '2028-01-02', '2028-12-31', pack_id, pack_version
                FROM findraft_year_ends
                WHERE id = :current
                """
            ),
            {"id": str(following_id), "current": year_end_id},
        )
        session.commit()
    later = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 12, 31),
        filename="later.xlsx",
    )
    following = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(later),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert following.status_code == 409, following.text
    assert "2027-12-31" in following.json()["detail"]
    assert "2028-01-02" in following.json()["detail"]
    assert "2028-01-01" in following.json()["detail"]

    clash = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2028, 1, 2),
        period_end=date(2028, 12, 31),
        filename="clash.xlsx",
    )
    collision = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(clash),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert collision.status_code == 409, collision.text
    assert collision.json()["detail"] == (
        "A statutory draft already exists for the period ending 2028-12-31. Open that draft."
    )

    overlap_tb = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 6, 1),
        period_end=date(2028, 5, 31),
        filename="overlap.xlsx",
    )
    overlap = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(overlap_tb),
            "row_version": row_version,
            "confirm": True,
        },
    )
    assert overlap.status_code == 409, overlap.text
    assert "overlaps" in overlap.json()["detail"]
    assert _year_end_row(year_end_id, org_id)["adopted"] == str(old_tb)
    assert _year_end_row(year_end_id, org_id)["period_end"] == "2026-12-31"


@pytest.mark.asyncio
async def test_switch_keeps_other_periods_face_dates_and_comparatives(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    assert isinstance(org_id, uuid.UUID)
    assert isinstance(company_id, uuid.UUID)
    year_end_id, draft_id, headers, _old = await _open(api_client, provisioned_org)
    other_tb = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2028, 1, 1),
        period_end=date(2028, 12, 31),
        filename="other.xlsx",
    )
    other = await api_client.post(
        f"/trial-balances/{other_tb}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert other.status_code == 200, other.text
    other_id = str(other.json()["year_end_id"])
    other_draft = await api_client.get(f"/year-ends/{other_id}/draft", headers=headers)
    other_draft_id = str(other_draft.json()["draft_id"])
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                """
                UPDATE findraft_draft_versions
                SET status = 'final',
                    snapshot = '{"kept": true}'::jsonb,
                    inputs_sha256 = :sha,
                    engine_sha = :sha
                WHERE id = :id
                """
            ),
            {"id": other_draft_id, "sha": "b" * 64},
        )
        session.execute(
            text(
                """
                UPDATE findraft_year_ends
                SET report_setup = '{"face_dates": {"current_start": "2026-01-01", "current_end": "2026-12-31"}}'::jsonb,
                    comparative_source_year_end_id = :other,
                    comparative_source_draft_id = :draft
                WHERE id = :id
                """
            ),
            {"id": year_end_id, "other": other_id, "draft": other_draft_id},
        )
        session.add(
            PriorYearLine(
                org_id=org_id,
                company_id=company_id,
                year_end_id=uuid.UUID(year_end_id),
                canonical_line="CASH",
                amount=Decimal("1.00"),
            )
        )
        session.commit()
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    new_tb = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=date(2027, 1, 1),
        period_end=date(2027, 12, 31),
        filename="moved.xlsx",
    )
    saved = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=headers,
        json={
            "trial_balance_id": str(new_tb),
            "row_version": draft.json()["row_version"],
            "confirm": True,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["adjustments_notice"] is None
    stored = _year_end_row(year_end_id, org_id)
    assert stored["source_year_end"] == other_id
    assert stored["source_draft"] == other_draft_id
    assert stored["report_setup"]["face_dates"]["current_start"] == "2026-01-01"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        kept = session.execute(
            text(
                "SELECT snapshot, status, period_end FROM findraft_draft_versions d JOIN findraft_year_ends y ON y.id = d.year_end_id WHERE d.id = :id"
            ),
            {"id": other_draft_id},
        ).one()
        prior_count = session.execute(
            text(
                "SELECT count(*) FROM findraft_prior_year_lines WHERE year_end_id = :id"
            ),
            {"id": year_end_id},
        ).scalar_one()
    assert kept.snapshot == {"kept": True}
    assert str(kept.period_end) == "2028-12-31"
    assert int(prior_count) == 1
    page = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance", headers=headers
    )
    assert page.json()["face_dates_notice"].startswith("The printed face dates differ")
    assert (
        "Review them on Prior-year comparatives" in page.json()["comparatives_notice"]
    )
    assert _draft_row(draft_id, org_id)["basis"] is None


@pytest.mark.asyncio
async def test_viewer_and_other_organisation_cannot_switch(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    year_end_id, _draft_id, headers, tb_id = await _open(api_client, provisioned_org)
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=org_id,
        clerk_org_id=str(provisioned_org["clerk_org_id"]),
        role="member",
        email_prefix="readopt-post",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=str(provisioned_org["clerk_org_id"]),
        role="owner",
        org_uuid=org_id,
    )
    _set_role(org_id=org_id, user_id=user_id, role="viewer")
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=auth_headers(token),
        json={"trial_balance_id": str(tb_id), "row_version": 1, "confirm": False},
    )
    assert refused.status_code == 403, refused.text
    readable = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance/candidates",
        headers=auth_headers(token),
    )
    assert readable.status_code == 200, readable.text

    suffix = uuid.uuid4().hex[:10]
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=f"org_readopt_{suffix}",
            org_name="Other practice",
            clerk_user_id=f"user_readopt_{suffix}",
            email=f"readopt-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id
        other_user = other.user.clerk_user_id
    other_token = make_access_token(
        clerk_user_id=other_user,
        clerk_org_id=f"org_readopt_{suffix}",
        org_uuid=other_org_id,
    )
    hidden = await api_client.post(
        f"/year-ends/{year_end_id}/trial-balance/adopt",
        headers=auth_headers(other_token),
        json={"trial_balance_id": str(tb_id), "row_version": 1, "confirm": True},
    )
    assert hidden.status_code == 404, hidden.text
    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        granted = _grant_append_only_delete(session)
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": str(other_org_id)},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(other_org_id)},
        )
        _revoke_append_only_delete(session, granted)
        session.commit()


def _tb_count(org_id: uuid.UUID) -> int:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        count = session.execute(
            text(
                """
                SELECT count(*) FROM trial_balances
                WHERE company_id IN (SELECT id FROM companies WHERE client_id IN (
                  SELECT id FROM clients WHERE org_id = :org
                ))
                """
            ),
            {"org": str(org_id)},
        ).scalar_one()
    return int(count)


@pytest.mark.asyncio
async def test_upload_requires_a_start_and_blocks_eighteen_months(
    api_client: AsyncClient, provisioned_org: dict[str, object]
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    headers = auth_headers(provisioned_org["token"])
    files = {
        "file": (
            "tb.xlsx",
            balanced_tb_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    before = _tb_count(org_id)
    missing = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_end": "2026-12-31",
            "currency": "GBP",
        },
        files=files,
    )
    assert missing.status_code == 422, missing.text
    assert missing.json()["detail"] == "Enter a period start and period end."
    assert _tb_count(org_id) == before
    too_long = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2026-01-01",
            "period_end": "2027-07-01",
            "currency": "GBP",
        },
        files=files,
    )
    assert too_long.status_code == 422, too_long.text
    assert too_long.json()["detail"] == (
        "This period is longer than 18 months. Statutory accounts will use these dates."
    )
    assert _tb_count(org_id) == before
    early = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_start": "2025-01-01",
            "period_end": "2025-12-31",
            "currency": "GBP",
        },
        files=files,
    )
    assert early.status_code == 202, early.text
    company_id = provisioned_org["company_id"]
    assert isinstance(company_id, uuid.UUID)
    kept = _insert_file(
        org_id=org_id,
        company_id=company_id,
        period_start=None,
        period_end=date(2024, 12, 31),
        filename=None,
    )
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        stored = session.get(TrialBalance, kept)
        assert stored is not None
        assert stored.period_start is None
