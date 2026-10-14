"""Note library: omit, force-include, notices, and an unchanged golden file."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.statutory_statements import build_statutory_statements
from tests.conftest import auth_headers, make_access_token
from tests.test_adopted_trial_balance import (
    _draft_version,
    _ready_golden,
    _snapshot,
)
from tests.test_organisations_api import _add_org_user
from tests.test_reconciliation import _lines
from tests.test_role_enforcement import _set_role
from tests.test_statutory_statements import _MAPPINGS, _TB, _entity, _golden

_FORBIDDEN = "You don't have permission to access this resource."
_PENSION_PLACEHOLDER = "[retirement benefit commitments not recorded]"
_ANSWERED_NO = {
    "COMMITMENTS_EXIST": False,
    "GUARANTEES_EXIST": False,
    "SUBSEQUENT_EVENTS": False,
    "PENSION_COMMITMENT": False,
    "CHARGES_EXIST": False,
    "OFF_BALANCE_ARRANGEMENT": False,
    "UNCOMMITTED": False,
    "HAS_FOREIGN": True,
}


def _library_column(draft_id: str, org_id: str) -> object:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        return session.execute(
            text("SELECT note_library FROM findraft_draft_versions WHERE id = :id"),
            {"id": draft_id},
        ).scalar_one()


def _clear_flag(draft_id: str, org_id: str, flag_name: str) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "DELETE FROM findraft_disclosure_answers "
                "WHERE draft_version_id = :id AND flag_name = :flag"
            ),
            {"id": draft_id, "flag": flag_name},
        )
        session.commit()


def _audit(org_id: str, draft_id: str, action: str) -> list[dict[str, object]]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        rows = (
            session.execute(
                text(
                    "SELECT new_value FROM audit_logs WHERE org_id = :org "
                    "AND entity_id = :draft AND action = :action ORDER BY chain_seq"
                ),
                {"org": org_id, "draft": draft_id, "action": action},
            )
            .scalars()
            .all()
        )
    assert all(isinstance(row, dict) for row in rows)
    return [row for row in rows if isinstance(row, dict)]


def _note_body(document: object, code: str) -> str:
    notes = getattr(document, "notes")
    note = next(item for item in notes if item.code == code)
    assert note.title
    assert note.body.strip()
    return str(note.body)


def test_catalogue_disambiguates_policy_blocks_from_notes() -> None:
    from app.services.note_library import _catalogue

    rows = list(_catalogue())
    entity = next(row for row in rows if row.block_id == "N0_ENTITY")
    assert entity.title == "Company information"
    assert entity.row_kind == "Note"
    debtors = {(row.row_kind, row.note_class) for row in rows if row.title == "Debtors"}
    creditors = {
        (row.row_kind, row.note_class) for row in rows if row.title == "Creditors"
    }
    assert debtors == {("Policy", "policies"), ("Note", "current assets")}
    assert creditors == {("Policy", "policies"), ("Note", "creditors")}
    for row in rows:
        assert row.title != row.block_id
        assert "N0_" not in row.title


def test_taxation_note_is_optional_and_defaults_off() -> None:
    from app.services.note_library import (
        LibraryRejected,
        NoteLibrary,
        _catalogue,
        _reason,
        _sentence,
        apply_library_action,
    )

    spec = next(row for row in _catalogue() if row.block_id == "taxation_note")
    assert spec.title == "Taxation"
    assert spec.controllable is True
    empty = NoteLibrary((), ())
    reason = _reason(spec, {}, empty, parent_pending=False)
    assert reason == "disclosure_no"
    sentence = _sentence(spec, reason, {})
    assert "optional for a small entity" in sentence
    assert "taxation_note" not in sentence
    added = apply_library_action(
        empty, block_id="taxation_note", action="add", ctx=_ANSWERED_NO
    )
    assert added.added == ("taxation_note",)
    assert _reason(spec, _ANSWERED_NO, added, parent_pending=False) == "added"
    with pytest.raises(LibraryRejected, match="this block is not included"):
        apply_library_action(
            empty, block_id="taxation_note", action="omit", ctx=_ANSWERED_NO
        )


def test_null_library_keeps_the_golden_notes_and_figures() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert document.omitted_blocks == ()
    assert document.added_blocks == ()
    commitments = _note_body(document, "N9_COMMITMENTS")
    assert commitments == "[commitments and contingencies not recorded]"
    assert not any(check.code.startswith("V-NOTE-") for check in document.checks)


def test_force_included_pension_prints_the_placeholder_and_a_notice() -> None:
    document = _golden(
        disclosure_flags=dict(_ANSWERED_NO),
        note_library={"omitted": [], "added": ["pension_commitments"]},
    )
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    body = _note_body(document, "N9_COMMITMENTS")
    assert "Retirement benefit commitments" in body
    assert "1AD.32" not in body
    assert _PENSION_PLACEHOLDER in body
    assert "[capital commitments not recorded]" not in body
    assert document.added_blocks == ("pension_commitments",)
    notice = next(check for check in document.checks if check.code == "V-NOTE-003")
    assert notice.severity == "NOTICE"
    assert notice.passed is False
    assert "Retirement benefit commitments" in notice.message
    assert "particulars are not recorded" in notice.message
    added = next(check for check in document.checks if check.code == "V-NOTE-002")
    assert added.severity == "NOTICE"
    assert "Added by the preparer" in added.message


def test_omitting_a_disclosure_policy_drops_only_that_paragraph() -> None:
    shown = _golden(disclosure_flags={"HAS_FOREIGN": True})
    hidden = _golden(
        disclosure_flags={"HAS_FOREIGN": True},
        note_library={"omitted": ["FOREIGN_CURRENCIES"], "added": []},
    )
    assert shown.net_assets == hidden.net_assets == Decimal("455812.00")
    assert shown.profit == hidden.profit == Decimal("157650.00")
    shown_policies = _note_body(shown, "N1_POLICIES")
    hidden_policies = _note_body(hidden, "N1_POLICIES")
    assert "Transactions in foreign currencies" in shown_policies
    assert "Transactions in foreign currencies" not in hidden_policies
    assert "Revenue is recognised" in hidden_policies
    assert hidden.omitted_blocks == ("FOREIGN_CURRENCIES",)
    notice = next(check for check in hidden.checks if check.code == "V-NOTE-001")
    assert notice.severity == "NOTICE"
    assert "Foreign currencies" in notice.message


def test_an_unanswered_addition_is_not_a_composed_block() -> None:
    document = build_statutory_statements(
        prior_year_validated=True,
        tb_lines=_lines(_TB),
        mappings=_MAPPINGS,
        prior_retained_earnings=Decimal("-322062.00"),
        prior_canonical={"RETAINED_EARNINGS": Decimal("-322062.00")},
        entity=_entity(),
        disclosure_flags={"PENSION_COMMITMENT": False},
        note_library={"omitted": [], "added": ["pension_commitments"]},
    )
    assert document.net_assets == Decimal("455812.00")
    body = _note_body(document, "N9_COMMITMENTS")
    assert body == "[commitments and contingencies not recorded]"
    assert _PENSION_PLACEHOLDER not in body
    assert document.added_blocks == ()


@pytest.mark.asyncio
async def test_library_routes_reject_bad_blocks_and_keep_golden_figures(
    api_client: AsyncClient,
    provisioned_org: dict[str, str],
) -> None:
    year_end_id, draft_id, headers = await _ready_golden(api_client, provisioned_org)
    org_id = provisioned_org["org_id"]
    notes_path = f"/year-ends/{year_end_id}/drafts/{draft_id}/notes"
    library_path = f"{notes_path}/library"
    listed = await api_client.get(notes_path, headers=headers)
    assert listed.status_code == 200, listed.text
    assert _library_column(draft_id, org_id) is None
    assert listed.json()["row_version"] == _draft_version(draft_id, org_id)
    rows = {row["block_id"]: row for row in listed.json()["rows"]}
    assert rows["N0_ENTITY"]["title"] == "Company information"
    assert rows["N0_ENTITY"]["kind"] == "Note"
    assert rows["N0_ENTITY"]["note_class"] == "other"
    assert rows["N0_ENTITY"]["sentence"] == "This note is always included."
    assert rows["DEBTORS"]["title"] == "Debtors"
    assert rows["DEBTORS"]["kind"] == "Policy"
    assert rows["DEBTORS"]["note_class"] == "policies"
    assert rows["N3_DEBTORS"]["title"] == "Debtors"
    assert rows["N3_DEBTORS"]["kind"] == "Note"
    assert rows["N3_DEBTORS"]["note_class"] == "current assets"
    assert rows["CREDITORS"]["kind"] == "Policy"
    assert rows["N4_CREDITORS"]["kind"] == "Note"
    for row in listed.json()["rows"]:
        assert row["title"] != row["block_id"]
        assert "N0_" not in row["title"]
    assert (
        rows["N2_FA"]["sentence"]
        == "Included because Tangible fixed assets has a balance."
    )
    assert rows["pension_commitments"]["sentence"] == (
        "Left out because the answer to "
        "“Are there retirement-benefit commitments?” is No."
    )
    assert rows["pension_commitments"]["can_add"] is True
    for row in listed.json()["rows"]:
        assert "£" not in row["sentence"]
        assert "€" not in row["sentence"]
        assert row["block_id"] not in row["sentence"]

    version = listed.json()["row_version"]
    for block_id in ("N0_ENTITY", "N2_FA", "NOT_A_BLOCK"):
        refused = await api_client.post(
            library_path,
            headers=headers,
            json={"row_version": version, "block_id": block_id, "action": "omit"},
        )
        assert refused.status_code == 422, refused.text
        assert _library_column(draft_id, org_id) is None

    _clear_flag(draft_id, org_id, "PENSION_COMMITMENT")
    waiting = await api_client.post(
        library_path,
        headers=headers,
        json={
            "row_version": version,
            "block_id": "pension_commitments",
            "action": "add",
        },
    )
    assert waiting.status_code == 422, waiting.text
    assert _library_column(draft_id, org_id) is None
    assert _audit(org_id, draft_id, "note_block_added") == []
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    assert any(
        check["code"] == "V-DISC-001" and check["passed"] is False
        for check in board.json()["checks"]
    )
    assert board.json()["can_finalise"] is False

    answered = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/disclosures",
        headers=headers,
        json={
            "row_version": board.json()["row_version"],
            "flag_name": "PENSION_COMMITMENT",
            "answer": "no",
        },
    )
    assert answered.status_code == 200, answered.text
    added = await api_client.post(
        library_path,
        headers=headers,
        json={
            "row_version": answered.json()["row_version"],
            "block_id": "pension_commitments",
            "action": "add",
        },
    )
    assert added.status_code == 200, added.text
    assert _audit(org_id, draft_id, "note_block_added") == [
        {"block_id": "pension_commitments"}
    ]
    again = await api_client.post(
        library_path,
        headers=headers,
        json={
            "row_version": added.json()["row_version"],
            "block_id": "pension_commitments",
            "action": "add",
        },
    )
    assert again.status_code == 422, again.text
    shown = await api_client.get(notes_path, headers=headers)
    pension = next(
        row for row in shown.json()["rows"] if row["block_id"] == "pension_commitments"
    )
    assert pension["reason"] == "added"
    assert pension["sentence"].startswith("Added by the preparer.")
    assert "is No." in pension["sentence"]

    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert statements.status_code == 200, statements.text
    body = statements.json()
    assert body["net_assets"] == "455812.00"
    assert body["profit"] == "157650.00"
    commitments = next(
        note for note in body["notes"] if note["code"] == "N9_COMMITMENTS"
    )
    assert commitments["title"]
    assert _PENSION_PLACEHOLDER in commitments["body"]
    assert "Retirement benefit commitments" in commitments["body"]
    assert "1AD.32" not in commitments["body"]
    assert body["added_blocks"] == ["pension_commitments"]
    codes = {check["code"] for check in body["checks"]}
    assert "V-NOTE-002" in codes
    assert "V-NOTE-003" in codes
    dashboard = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert dashboard.json()["can_finalise"] is True
    question = next(
        item
        for item in dashboard.json()["disclosure_questions"]
        if item["flag_name"] == "PENSION_COMMITMENT"
    )
    assert question["answer"] == "no"

    foreign = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/disclosures",
        headers=headers,
        json={
            "row_version": dashboard.json()["row_version"],
            "flag_name": "HAS_FOREIGN",
            "answer": "yes",
        },
    )
    assert foreign.status_code == 200, foreign.text
    omitted = await api_client.post(
        library_path,
        headers=headers,
        json={
            "row_version": foreign.json()["row_version"],
            "block_id": "FOREIGN_CURRENCIES",
            "action": "omit",
        },
    )
    assert omitted.status_code == 200, omitted.text
    after = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    policies = next(
        note for note in after.json()["notes"] if note["code"] == "N1_POLICIES"
    )
    assert "Transactions in foreign currencies" not in policies["body"]
    assert "Revenue is recognised" in policies["body"]
    assert after.json()["net_assets"] == "455812.00"
    assert after.json()["profit"] == "157650.00"

    viewer_id, viewer_clerk, _issued = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="library-viewer",
    )
    viewer_headers = auth_headers(
        make_access_token(
            clerk_user_id=viewer_clerk,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="owner",
            org_uuid=org_id,
        )
    )
    _set_role(org_id=org_id, user_id=viewer_id, role="viewer")
    viewer = await api_client.post(
        library_path,
        headers=viewer_headers,
        json={
            "row_version": omitted.json()["row_version"],
            "block_id": "pension_commitments",
            "action": "remove",
        },
    )
    assert viewer.status_code == 403
    assert viewer.json()["detail"] == _FORBIDDEN
    missing = await api_client.get(
        f"/year-ends/{uuid.uuid4()}/drafts/{draft_id}/notes",
        headers=headers,
    )
    assert missing.status_code == 404

    finalised = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": "note-library-final"},
        json={"row_version": omitted.json()["row_version"]},
    )
    assert finalised.status_code == 200, finalised.text
    stored = _snapshot(draft_id, org_id)
    assert stored is not None
    assert stored["note_library"] == {
        "added": ["pension_commitments"],
        "omitted": ["FOREIGN_CURRENCIES"],
    }
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE findraft_draft_versions SET note_library = NULL WHERE id = :id"
            ),
            {"id": draft_id},
        )
        session.commit()
    kept = _snapshot(draft_id, org_id)
    assert kept is not None
    assert kept["note_library"] == stored["note_library"]
