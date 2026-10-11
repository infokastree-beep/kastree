"""Disclosure question groups, mark-remaining-no, and the answer audit."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.services.disclosure_groups import (
    catalogue_flags,
    present_disclosure_questions,
)
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from findraft.engine.notes import ANSWER_FLAGS, DERIVED
from tests.conftest import auth_headers, make_access_token
from tests.test_draft_locking import _draft_path
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


def test_catalogue_is_the_preparer_flags() -> None:
    assert catalogue_flags() == set(ANSWER_FLAGS)
    assert catalogue_flags().isdisjoint(DERIVED)


def test_questions_use_the_pack_sentence_and_leave_missing_unanswered() -> None:
    rows = present_disclosure_questions({"PENSION_COMMITMENT": True, "FIXED_ASSETS_NBV": True})
    by_flag = {row.flag_name: row for row in rows}
    assert set(by_flag) == set(ANSWER_FLAGS)
    pension = by_flag["PENSION_COMMITMENT"]
    assert pension.question == "Are there retirement-benefit commitments?"
    assert pension.group == "Commitments"
    assert pension.note == "N9_COMMITMENTS"
    assert pension.answer == "yes"
    assert by_flag["CHARGES_EXIST"].answer == "unanswered"
    assert by_flag["HAS_FOREIGN"].group == "Other"
    assert by_flag["HAS_FOREIGN"].question == "Did the company have foreign-currency items?"
    assert by_flag["COMMITMENTS_EXIST"].group == "Commitments"
    assert by_flag["REVALUATION_RESERVE"].question == "Is there a revaluation reserve?"
    assert (
        by_flag["GUARANTEES_EXIST"].question
        == "Has the company given guarantees or security?"
    )
    assert "FIXED_ASSETS_NBV" not in by_flag


def _audit_values(org_id: str, draft_id: str, action: str) -> list[dict[str, object]]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        rows = session.execute(
            text(
                "SELECT new_value FROM audit_logs WHERE org_id = :org "
                "AND entity_id = :draft AND action = :action "
                "ORDER BY chain_seq"
            ),
            {"org": org_id, "draft": draft_id, "action": action},
        ).scalars().all()
    assert all(isinstance(row, dict) for row in rows)
    return [row for row in rows if isinstance(row, dict)]


@pytest.mark.asyncio
async def test_mark_remaining_no_writes_only_unanswered_flags(
    api_client: AsyncClient,
    provisioned_org: dict[str, str],
    stored_files: LocalPracticeStorage,
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
    board = await api_client.get(
        _draft_path(year_end_id, draft_id, "dashboard"), headers=headers
    )
    assert board.status_code == 200, board.text
    payload = board.json()
    questions = payload["disclosure_questions"]
    assert {row["flag_name"] for row in questions} == set(ANSWER_FLAGS)
    assert payload["unanswered_count"] == len(payload["unanswered_disclosures"])
    assert set(payload["unanswered_disclosures"]) <= {row["flag_name"] for row in questions}
    assert all(row["answer"] == "unanswered" for row in questions)
    row_version = payload["row_version"]

    refused = await api_client.post(
        _draft_path(year_end_id, draft_id, "disclosures/mark-remaining-no"),
        headers=headers,
        json={"row_version": row_version, "confirm": False},
    )
    assert refused.status_code == 422, refused.text
    assert _audit_values(
        provisioned_org["org_id"], draft_id, "disclosures_marked_remaining_no"
    ) == []

    saved = await api_client.post(
        _draft_path(year_end_id, draft_id, "disclosures"),
        headers=headers,
        json={
            "row_version": row_version,
            "flag_name": "PENSION_COMMITMENT",
            "answer": "yes",
        },
    )
    assert saved.status_code == 200, saved.text
    answered = _audit_values(
        provisioned_org["org_id"], draft_id, "disclosure_answered"
    )
    assert answered == [{"flag_name": "PENSION_COMMITMENT", "answer": "yes"}]
    assert "amount" not in answered[0]
    row_version = saved.json()["row_version"]

    marked = await api_client.post(
        _draft_path(year_end_id, draft_id, "disclosures/mark-remaining-no"),
        headers=headers,
        json={"row_version": row_version, "confirm": True},
    )
    assert marked.status_code == 200, marked.text
    body = marked.json()
    assert body["count"] == len(ANSWER_FLAGS) - 1
    assert "PENSION_COMMITMENT" not in body["flag_ids"]
    assert sorted(body["flag_ids"]) == body["flag_ids"]
    recorded = _audit_values(
        provisioned_org["org_id"], draft_id, "disclosures_marked_remaining_no"
    )
    assert len(recorded) == 1
    assert recorded[0]["count"] == body["count"]
    assert recorded[0]["flag_ids"] == body["flag_ids"]
    assert "FIXED_ASSETS_NBV" not in recorded[0]["flag_ids"]

    again = await api_client.get(
        _draft_path(year_end_id, draft_id, "dashboard"), headers=headers
    )
    assert again.status_code == 200, again.text
    after = {row["flag_name"]: row["answer"] for row in again.json()["disclosure_questions"]}
    assert after["PENSION_COMMITMENT"] == "yes"
    assert after["HAS_FOREIGN"] == "no"
    assert again.json()["unanswered_count"] == 0

    empty = await api_client.post(
        _draft_path(year_end_id, draft_id, "disclosures/mark-remaining-no"),
        headers=headers,
        json={"row_version": again.json()["row_version"], "confirm": True},
    )
    assert empty.status_code == 422, empty.text
    assert (
        len(
            _audit_values(
                provisioned_org["org_id"],
                draft_id,
                "disclosures_marked_remaining_no",
            )
        )
        == 1
    )

    viewer_id, viewer_clerk, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="disclosure-viewer",
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
        _draft_path(year_end_id, draft_id, "disclosures/mark-remaining-no"),
        headers=viewer_headers,
        json={"row_version": again.json()["row_version"], "confirm": True},
    )
    assert viewer_post.status_code == 403
    assert viewer_post.json()["detail"] == _FORBIDDEN

    statements = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["net_assets"] == "455812.00"
    assert statements.json()["profit"] == "157650.00"
