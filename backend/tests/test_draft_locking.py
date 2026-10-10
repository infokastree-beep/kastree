"""Week 10: adjustments, disclosure answers, lock, and a FINAL snapshot."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.services.draft_workflow import engine_sha
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_statutory_statements import _ready_golden, _statements_path
from tests.test_tb_ingestion import _year_end

_FORBIDDEN = "You don't have permission to access this resource."


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _draft_path(year_end_id: str, draft_id: str, action: str = "") -> str:
    suffix = f"/{action}" if action else ""
    return f"/year-ends/{year_end_id}/drafts/{draft_id}{suffix}"


def _balanced(row_version: int, narration: str = "Reclass debtors and cash") -> dict:
    return {
        "row_version": row_version,
        "narration": narration,
        "lines": [
            {
                "nominal_code": "2110",
                "account_name": "Other debtors",
                "canonical_line": "OTHER_DEBTORS",
                "debit": "10.00",
                "credit": "0.00",
            },
            {
                "nominal_code": "2130",
                "account_name": "Bank current account",
                "canonical_line": "CASH",
                "debit": "0.00",
                "credit": "10.00",
            },
        ],
    }


def _face(payload: dict, label: str) -> Decimal:
    row = next(item for item in payload["sofp"] if item["label"] == label)
    return Decimal(row["current"])


async def _answer_disclosures(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    draft_id: str,
    row_version: int,
) -> int:
    for _ in range(8):
        board = await api_client.get(
            _draft_path(year_end_id, draft_id, "dashboard"), headers=headers
        )
        assert board.status_code == 200, board.text
        pending = board.json()["unanswered_disclosures"]
        row_version = board.json()["row_version"]
        if not pending:
            return row_version
        for name in pending:
            saved = await api_client.post(
                _draft_path(year_end_id, draft_id, "disclosures"),
                headers=headers,
                json={
                    "row_version": row_version,
                    "flag_name": name,
                    "answer": "no",
                },
            )
            assert saved.status_code == 200, saved.text
            row_version = saved.json()["row_version"]
    raise AssertionError("disclosure questions did not clear")


@pytest.mark.asyncio
async def test_week10_lock_adjust_and_freeze_final(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    headers = auth_headers(provisioned_org["token"])
    version = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}",
        headers=headers,
    )
    assert version.status_code == 200, version.text
    draft_id = version.json()["draft_id"]
    assert draft_id
    assert version.json()["draft_version_number"] == 1
    opened = await api_client.get(f"/year-ends/{year_end_id}", headers=headers)
    assert opened.status_code == 200, opened.text
    working = await api_client.get(
        f"/year-ends/{year_end_id}/draft", headers=headers
    )
    assert working.status_code == 200, working.text
    assert working.json()["draft_id"] == draft_id
    assert working.json()["status"] == "draft"
    assert working.json()["tb_version_id"] == version_id

    before = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert before.status_code == 200, before.text
    assert before.json()["watermark"] == "DRAFT"
    assert before.json()["renderable"] is True
    assert before.json()["net_assets"] == "455812.00"
    assert before.json()["profit"] == "157650.00"
    debtors_before = _face(before.json(), "Other debtors")
    creditors_before = _face(
        before.json(), "Creditors: amounts falling due within one year"
    )
    cash_before = _face(before.json(), "Cash at bank and in hand")

    board = await api_client.get(
        _draft_path(year_end_id, draft_id, "dashboard"), headers=headers
    )
    assert board.status_code == 200, board.text
    assert board.json()["traffic"] == "red"
    assert board.json()["can_finalise"] is False
    assert board.json()["row_version"] == 1
    disc = next(item for item in board.json()["checks"] if item["code"] == "V-DISC-001")
    assert disc["passed"] is False
    assert disc["severity"] == "CRITICAL"

    missing_key = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers=headers,
        json=_balanced(1),
    )
    assert missing_key.status_code == 400

    unbalanced = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-unbalanced"},
        json={
            "row_version": 1,
            "narration": "Does not balance",
            "lines": [
                {
                    "nominal_code": "2110",
                    "account_name": "Other debtors",
                    "canonical_line": "OTHER_DEBTORS",
                    "debit": "10.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "2130",
                    "account_name": "Bank current account",
                    "canonical_line": "CASH",
                    "debit": "0.00",
                    "credit": "5.00",
                },
            ],
        },
    )
    assert unbalanced.status_code == 400, unbalanced.text
    assert "does not balance" in unbalanced.json()["detail"]

    hostile = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-hostile"},
        json={
            "row_version": 1,
            "narration": "Not a statutory line",
            "lines": [
                {
                    "nominal_code": "8800",
                    "account_name": "Suspense",
                    "canonical_line": "not_a_real_line",
                    "debit": "10.00",
                    "credit": "0.00",
                },
                {
                    "nominal_code": "8801",
                    "account_name": "Suspense credit",
                    "canonical_line": "CASH",
                    "debit": "0.00",
                    "credit": "10.00",
                },
            ],
        },
    )
    assert hostile.status_code == 400, hostile.text
    assert "not a statutory line" in hostile.json()["detail"]

    conflict = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-conflict"},
        json={
            "row_version": 1,
            "narration": "Wrong line for an existing code",
            "lines": [
                {
                    "nominal_code": "2110",
                    "account_name": "Other debtors",
                    "canonical_line": "REVENUE",
                    "debit": "0.00",
                    "credit": "10.00",
                },
                {
                    "nominal_code": "2130",
                    "account_name": "Bank current account",
                    "canonical_line": "CASH",
                    "debit": "10.00",
                    "credit": "0.00",
                },
            ],
        },
    )
    assert conflict.status_code == 400, conflict.text
    assert "already mapped" in conflict.json()["detail"]

    viewer_id, viewer_clerk, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="week10-viewer",
    )
    viewer_headers = auth_headers(
        make_access_token(
            clerk_user_id=viewer_clerk,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="owner",
            org_uuid=provisioned_org["org_id"],
        )
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=viewer_id, role="viewer")
    viewer_post = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**viewer_headers, "Idempotency-Key": "week10-viewer"},
        json=_balanced(1),
    )
    assert viewer_post.status_code == 403
    assert viewer_post.json()["detail"] == _FORBIDDEN

    posted = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-adjust"},
        json=_balanced(1),
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["row_version"] == 2
    journal_id = posted.json()["journal_id"]

    replay = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-adjust"},
        json=_balanced(1),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["journal_id"] == journal_id
    assert replay.json()["row_version"] == 2

    clash = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-adjust"},
        json=_balanced(2, "A different narration"),
    )
    assert clash.status_code == 409

    stale = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**headers, "Idempotency-Key": "week10-stale"},
        json=_balanced(1, "Stale version"),
    )
    assert stale.status_code == 409
    assert "row_version" in stale.json()["detail"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        count = session.execute(
            text(
                "SELECT count(*) FROM findraft_adjustment_journals "
                "WHERE draft_version_id = :id"
            ),
            {"id": draft_id},
        ).scalar_one()
        operations = session.execute(
            text(
                "SELECT count(*) FROM findraft_draft_operations "
                "WHERE org_id = :org AND idempotency_key = 'week10-adjust' "
                "AND action = 'adjust'"
            ),
            {"org": str(provisioned_org["org_id"])},
        ).scalar_one()
        assert count == 1
        assert operations == 1

    moved = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["watermark"] == "DRAFT"
    assert moved.json()["net_assets"] == "455812.00"
    assert moved.json()["profit"] == "157650.00"
    # A credit-only cash line is its own source. The engine homes that
    # negative balance to bank overdraft, so cash on the face stays put,
    # other debtors rise, and creditors within one year move by the same 10.
    assert _face(moved.json(), "Cash at bank and in hand") == cash_before
    assert _face(moved.json(), "Other debtors") == debtors_before + Decimal("10.00")
    assert _face(
        moved.json(), "Creditors: amounts falling due within one year"
    ) == creditors_before - Decimal("10.00")

    evidence = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}/evidence", headers=headers
    )
    assert evidence.status_code == 200, evidence.text
    body = evidence.json()
    assert [document["role"] for document in body["documents"]] == ["trial_balance"]
    adjustment_accounts = [
        account
        for line in body["lines"]
        for account in line["accounts"]
        if account["nominal_code"] == "2110" and account["balance"] == "10.00"
    ]
    assert adjustment_accounts
    assert adjustment_accounts[0]["tb_line_id"] is None
    assert adjustment_accounts[0]["source_document_id"] == body["documents"][0]["id"]

    row_version = await _answer_disclosures(
        api_client, headers, year_end_id, draft_id, 2
    )
    approved = await api_client.put(
        f"/year-ends/{year_end_id}/approval",
        headers=headers,
        json={
            "approval_date": "2027-03-15",
            "signing_directors": ["Ada Lovelace"],
        },
    )
    assert approved.status_code == 200, approved.text
    ready = await api_client.get(
        _draft_path(year_end_id, draft_id, "dashboard"), headers=headers
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["unanswered_disclosures"] == []
    assert ready.json()["traffic"] in {"amber", "green"}
    assert ready.json()["can_finalise"] is True
    disc_after = next(
        item for item in ready.json()["checks"] if item["code"] == "V-DISC-001"
    )
    assert disc_after["passed"] is True

    recomputed = await api_client.post(
        _draft_path(year_end_id, draft_id, "recompute"),
        headers={**headers, "Idempotency-Key": "week10-recompute"},
        json={"row_version": row_version},
    )
    assert recomputed.status_code == 200, recomputed.text
    assert recomputed.json()["row_version"] == row_version + 1
    assert recomputed.json()["can_finalise"] is True
    replayed = await api_client.post(
        _draft_path(year_end_id, draft_id, "recompute"),
        headers={**headers, "Idempotency-Key": "week10-recompute"},
        json={"row_version": row_version},
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["row_version"] == row_version + 1
    row_version = recomputed.json()["row_version"]

    member_id, member_clerk, _member_issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="week10-member",
    )
    member_headers = auth_headers(
        make_access_token(
            clerk_user_id=member_clerk,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="owner",
            org_uuid=provisioned_org["org_id"],
        )
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=member_id, role="member")
    member_final = await api_client.post(
        _draft_path(year_end_id, draft_id, "finalise"),
        headers={**member_headers, "Idempotency-Key": "week10-member-final"},
        json={"row_version": row_version},
    )
    assert member_final.status_code == 403
    assert member_final.json()["detail"] == _FORBIDDEN

    locked = await api_client.post(
        _draft_path(year_end_id, draft_id, "lock"),
        headers=member_headers,
        json={"row_version": row_version},
    )
    assert locked.status_code == 200, locked.text
    assert locked.json()["status"] == "locked"
    locked_version = locked.json()["row_version"]

    refused = await api_client.post(
        _draft_path(year_end_id, draft_id, "adjustments"),
        headers={**member_headers, "Idempotency-Key": "week10-after-lock"},
        json=_balanced(locked_version, "After lock"),
    )
    assert refused.status_code == 409

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        with pytest.raises(DBAPIError, match="mapping writes are refused"):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_confirmed_mappings (
                      id, org_id, company_id, tb_version_id,
                      nominal_code, canonical_line
                    ) VALUES (
                      :id, :org, :company, :version, '9991', 'CASH'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(provisioned_org["org_id"]),
                    "company": str(provisioned_org["company_id"]),
                    "version": version_id,
                },
            )
            session.commit()
        session.rollback()

    created = await api_client.post(
        _draft_path(year_end_id, draft_id, "new-version"),
        headers=member_headers,
        json={"row_version": locked_version},
    )
    assert created.status_code == 200, created.text
    assert created.json()["status"] == "draft"
    assert created.json()["version_number"] == 2
    assert created.json()["row_version"] == 1
    new_id = created.json()["draft_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        journal_id_raw = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO findraft_adjustment_journals (
                  id, org_id, company_id, draft_version_id, narration
                ) VALUES (:id, :org, :company, :draft, 'one sided')
                """
            ),
            {
                "id": str(journal_id_raw),
                "org": str(provisioned_org["org_id"]),
                "company": str(provisioned_org["company_id"]),
                "draft": new_id,
            },
        )
        session.execute(
            text(
                """
                INSERT INTO findraft_adjustment_lines (
                  id, org_id, company_id, journal_id, draft_version_id, line_no,
                  nominal_code, account_name, canonical_line, debit, credit
                ) VALUES (
                  :id, :org, :company, :journal, :draft, 1,
                  '2110', 'Other debtors', 'OTHER_DEBTORS', 10.00, 0
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(provisioned_org["org_id"]),
                "company": str(provisioned_org["company_id"]),
                "journal": str(journal_id_raw),
                "draft": new_id,
            },
        )
        with pytest.raises(DBAPIError, match="does not balance"):
            session.commit()
        session.rollback()

    copied = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert copied.status_code == 200, copied.text
    assert _face(copied.json(), "Other debtors") == debtors_before + Decimal("10.00")

    final = await api_client.post(
        _draft_path(year_end_id, new_id, "finalise"),
        headers={**headers, "Idempotency-Key": "week10-final"},
        json={"row_version": 1, "reviewed_carried_disclosures": True},
    )
    assert final.status_code == 200, final.text
    stored = final.json()
    assert stored["status"] == "final"
    assert stored["traffic"] in {"amber", "green"}
    assert stored["pack_id"] == "frs102-1a-ie"
    assert len(stored["inputs_sha256"]) == 64
    assert stored["engine_sha"] == engine_sha()

    again = await api_client.post(
        _draft_path(year_end_id, new_id, "finalise"),
        headers={**headers, "Idempotency-Key": "week10-final"},
        json={"row_version": 1, "reviewed_carried_disclosures": True},
    )
    assert again.status_code == 200, again.text
    assert again.json()["row_version"] == stored["row_version"]

    second_key = await api_client.post(
        _draft_path(year_end_id, new_id, "finalise"),
        headers={**headers, "Idempotency-Key": "week10-final-again"},
        json={"row_version": stored["row_version"]},
    )
    assert second_key.status_code == 409

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("FINAL output was recomputed")

    monkeypatch.setattr("app.routers.year_ends.statements_for_version", _explode)
    monkeypatch.setattr("app.routers.year_ends.evidence_for_version", _explode)
    monkeypatch.setattr("app.services.statutory_statements.aggregate", _explode)
    monkeypatch.setattr("app.services.statutory_evidence.aggregate", _explode)
    monkeypatch.setattr("app.services.reconciliation.aggregate", _explode)

    frozen = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["watermark"] == "FINAL"
    assert frozen.json()["net_assets"] == "455812.00"
    assert frozen.json()["profit"] == "157650.00"
    assert _face(frozen.json(), "Other debtors") == debtors_before + Decimal("10.00")

    frozen_pdf = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}.pdf", headers=headers
    )
    assert frozen_pdf.status_code == 200, frozen_pdf.text
    assert "statutory-statements-final.pdf" in frozen_pdf.headers["content-disposition"]
    assert frozen_pdf.content.startswith(b"%PDF")

    frozen_evidence = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}/evidence", headers=headers
    )
    assert frozen_evidence.status_code == 200, frozen_evidence.text
    frozen_body = frozen_evidence.json()
    assert [document["role"] for document in frozen_body["documents"]] == [
        "trial_balance"
    ]
    frozen_adjustment = [
        account
        for line in frozen_body["lines"]
        for account in line["accounts"]
        if account["nominal_code"] == "2110" and account["balance"] == "10.00"
    ]
    assert frozen_adjustment
    assert frozen_adjustment[0]["tb_line_id"] is None

    frozen_board = await api_client.get(
        _draft_path(year_end_id, new_id, "dashboard"), headers=headers
    )
    assert frozen_board.status_code == 200, frozen_board.text
    assert frozen_board.json()["status"] == "final"
    assert frozen_board.json()["can_finalise"] is False
    assert frozen_board.json()["traffic"] == stored["traffic"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        with pytest.raises(DBAPIError, match="FINAL draft is immutable"):
            session.execute(
                text(
                    """
                    UPDATE findraft_draft_versions
                    SET status = 'draft'
                    WHERE id = :id
                    """
                ),
                {"id": new_id},
            )
            session.commit()
        session.rollback()
