"""Note particulars are typed, printed under the pack sentence, and gated on Yes.

Companies Act 2014, sections 305 to 308. The wording status stays researched
from the public Act. Golden figures stay put. The database role is findraft.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.services.company_details import blocks_final
from app.services.particulars import particulars_checks
from app.services.statutory_docx import build_docx
from app.services.statutory_statements import NoteParticulars
from findraft.models.draft_version import DraftVersion
from tests.conftest import auth_headers
from tests.test_organisations_api import _add_org_user
from tests.test_statutory_statements import _golden

_FORBIDDEN = "You don't have permission to access this resource."
_FINAL = "This draft is final. It cannot be changed."
_LOCKED = "This draft is locked. It cannot be changed."
_FROZEN = "This draft is frozen. It cannot be changed."
_FLAGS = {
    "RPT_EXISTS": True,
    "DIRECTORS_EXIST": True,
    "CONNECTED_LOANS": True,
    "GUARANTEES_EXIST": True,
    "SUBSEQUENT_EVENTS": True,
    "DIRECTOR_GUARANTEES": True,
    "COMMITMENTS_EXIST": False,
    "PENSION_COMMITMENT": False,
    "CHARGES_EXIST": False,
    "OFF_BALANCE_ARRANGEMENT": False,
}
_TEXT = NoteParticulars(
    related_party="Rent was charged.",
    directors_remuneration="Aggregate remuneration was recorded.",
    loan_terms="A loan was outstanding.",
    guarantees="A bank guarantee was given.",
    subsequent_events="A lease was signed.",
)


def _print_role() -> None:
    with SyncSessionLocal() as session:
        role = session.execute(text("SELECT current_user")).scalar_one()
    assert role == "findraft"


def _note(document: object, code: str) -> str:
    notes = getattr(document, "notes")
    return next(note.body for note in notes if note.code == code)


def test_yes_with_an_empty_slot_blocks_final_and_a_filled_slot_does_not() -> None:
    empty = SimpleNamespace(
        related_party_particulars=None,
        directors_remuneration_particulars="   ",
        loan_terms_particulars=None,
        guarantee_particulars=None,
    )
    blocked = particulars_checks(empty, _FLAGS)
    assert {item.code for item in blocked if not item.passed} == {
        "V-CO-040",
        "V-CO-041",
        "V-CO-042",
        "V-CO-043",
    }
    assert "sections 305 and 306" in next(
        item.message for item in blocked if item.code == "V-CO-041"
    )
    assert "sections 307 and 308" in next(
        item.message for item in blocked if item.code == "V-CO-042"
    )
    assert blocks_final(blocked) is True
    quiet = particulars_checks(empty, {"RPT_EXISTS": False, "DIRECTORS_EXIST": False})
    assert quiet == ()
    filled = SimpleNamespace(
        related_party_particulars="Rent was charged.",
        directors_remuneration_particulars="Recorded.",
        loan_terms_particulars="A loan was outstanding.",
        guarantee_particulars="A bank guarantee was given.",
    )
    done = particulars_checks(filled, _FLAGS)
    assert all(item.passed for item in done)
    assert blocks_final(done) is False


def test_particulars_print_under_the_pack_sentence_and_keep_golden_figures(
    tmp_path,
) -> None:
    document = _golden(disclosure_flags=_FLAGS, note_particulars=_TEXT)
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    related = _note(document, "N7_RPT")
    assert "sections 305 and 306" in related
    assert "Rent was charged." in related
    assert "Aggregate remuneration was recorded." in related
    assert "[related party transactions not recorded]" not in related
    assert "[directors' aggregate disclosures not recorded]" not in related
    loans = _note(document, "N5_LOANS")
    assert "sections 307 and 308" in loans
    assert "A loan was outstanding." in loans
    assert "A bank guarantee was given." in loans
    commitments = _note(document, "N9_COMMITMENTS")
    assert "Guarantees and security\nA bank guarantee was given." in commitments
    assert "Subsequent events\nA lease was signed." in commitments
    assert "[guarantees and security not recorded]" not in commitments
    assert "[subsequent events not recorded]" not in commitments
    assert document.html is not None
    assert "Rent was charged." in document.html
    assert "A lease was signed." in document.html
    dest = tmp_path / "particulars.docx"
    build_docx(
        {
            "watermark": "DRAFT",
            "company_name": "Harbour Limited",
            "pages": [],
            "sofp": [],
            "income": [],
            "notes": [
                {"code": "N7_RPT", "title": "Related parties", "body": related},
                {"code": "N9_COMMITMENTS", "title": "Commitments", "body": commitments},
            ],
        },
        dest,
    )
    with ZipFile(dest) as archive:
        xml = archive.read("word/document.xml").decode()
    assert "Rent was charged." in xml
    assert "A lease was signed." in xml


def test_an_empty_yes_keeps_the_placeholder_and_the_golden_figures() -> None:
    document = _golden(
        disclosure_flags={
            "RPT_EXISTS": True,
            "CONNECTED_LOANS": True,
            "GUARANTEES_EXIST": True,
            "SUBSEQUENT_EVENTS": True,
            "COMMITMENTS_EXIST": False,
            "PENSION_COMMITMENT": False,
            "CHARGES_EXIST": False,
            "OFF_BALANCE_ARRANGEMENT": False,
        }
    )
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert "[related party transactions not recorded]" in _note(document, "N7_RPT")
    assert _note(document, "N5_LOANS").endswith(
        "sections 307 and 308 of the Companies Act 2014. "
        "[loans and credit particulars not recorded]"
    )
    commitments = _note(document, "N9_COMMITMENTS")
    assert "[guarantees and security not recorded]" in commitments
    assert "[subsequent events not recorded]" in commitments


def _set_draft(
    *,
    org_id: uuid.UUID,
    year_end_id: str,
    status: str,
    frozen: bool,
) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        updated = session.execute(
            text(
                """
                UPDATE findraft_draft_versions
                SET status = :status,
                    is_frozen = :frozen,
                    snapshot = CASE
                      WHEN :status = 'final' THEN COALESCE(snapshot, CAST('{}' AS jsonb))
                      ELSE snapshot
                    END,
                    inputs_sha256 = CASE
                      WHEN :status = 'final' THEN :sha
                      ELSE inputs_sha256
                    END,
                    engine_sha = CASE
                      WHEN :status = 'final' THEN :sha
                      ELSE engine_sha
                    END
                WHERE org_id = :org AND year_end_id = :year_end
                """
            ),
            {
                "status": status,
                "frozen": frozen,
                "org": str(org_id),
                "year_end": year_end_id,
                "sha": "a" * 64,
            },
        )
        assert updated.rowcount == 1
        session.commit()


@pytest.mark.asyncio
async def test_a_member_saves_particulars_and_a_closed_draft_refuses(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    _print_role()
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Harbour Trading Limited"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]
    opened = await api_client.post(
        "/year-ends",
        headers=headers,
        json={
            "company_id": company_id,
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )
    assert opened.status_code == 201, opened.text
    year_end_id = opened.json()["id"]
    loaded = await api_client.get(f"/year-ends/{year_end_id}", headers=headers)
    assert loaded.status_code == 200, loaded.text
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            DraftVersion(
                org_id=org_id,
                company_id=uuid.UUID(company_id),
                year_end_id=uuid.UUID(year_end_id),
                version_number=1,
                pack_id=loaded.json()["pack_id"],
                pack_version=loaded.json()["pack_version"],
                status="draft",
                is_frozen=False,
            )
        )
        session.commit()
    member_id, _clerk, member_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="particulars-member",
    )
    member_headers = auth_headers(member_token)
    _viewer_id, _viewer_clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="particulars-viewer",
    )
    body = {
        "related_party_particulars": "Rent was charged.",
        "directors_remuneration_particulars": "Aggregate remuneration was recorded.",
        "loan_terms_particulars": "A loan was outstanding.",
        "guarantee_particulars": "A bank guarantee was given.",
        "subsequent_events_particulars": "A lease was signed.",
        "share_classes": [
            {
                "class_name": "Ordinary",
                "authorised_number": None,
                "issued_number": 7,
                "nominal_value": "1.50",
            }
        ],
    }
    refused = await api_client.put(
        f"/year-ends/{year_end_id}/particulars",
        headers=auth_headers(viewer_token),
        json=body,
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN
    too_long = await api_client.put(
        f"/year-ends/{year_end_id}/particulars",
        headers=member_headers,
        json={**body, "related_party_particulars": "x" * 2001},
    )
    assert too_long.status_code == 400, too_long.text
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/particulars",
        headers=member_headers,
        json=body,
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["related_party_particulars"] == "Rent was charged."
    assert payload["directors_remuneration_particulars"] == (
        "Aggregate remuneration was recorded."
    )
    assert payload["loan_terms_particulars"] == "A loan was outstanding."
    assert payload["guarantee_particulars"] == "A bank guarantee was given."
    assert payload["subsequent_events_particulars"] == "A lease was signed."
    assert payload["share_classes"][0]["issued_amount"] == "10.50"
    assert isinstance(member_id, uuid.UUID)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text(
                """
                SELECT user_id::text, new_value
                FROM audit_logs
                WHERE org_id = :org AND action = 'particulars_saved'
                  AND entity_id = :year_end
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"org": str(org_id), "year_end": year_end_id},
        ).one()
    assert row.user_id == str(member_id)
    recorded = str(row.new_value)
    assert "Rent was charged." not in recorded
    assert "1.50" not in recorded
    assert row.new_value["related_party_recorded"] is True
    assert row.new_value["share_classes"] == [
        {"class_name": "Ordinary", "authorised_number": None, "issued_number": 7}
    ]
    _set_draft(org_id=org_id, year_end_id=year_end_id, status="locked", frozen=False)
    locked = await api_client.put(
        f"/year-ends/{year_end_id}/particulars",
        headers=member_headers,
        json=body,
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"] == _LOCKED
    _set_draft(org_id=org_id, year_end_id=year_end_id, status="final", frozen=False)
    final = await api_client.put(
        f"/year-ends/{year_end_id}/particulars",
        headers=member_headers,
        json=body,
    )
    assert final.status_code == 409, final.text
    assert final.json()["detail"] == _FINAL
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            DraftVersion(
                org_id=org_id,
                company_id=uuid.UUID(company_id),
                year_end_id=uuid.UUID(year_end_id),
                version_number=2,
                pack_id=loaded.json()["pack_id"],
                pack_version=loaded.json()["pack_version"],
                status="draft",
                is_frozen=True,
            )
        )
        session.commit()
    frozen = await api_client.put(
        f"/year-ends/{year_end_id}/particulars",
        headers=member_headers,
        json=body,
    )
    assert frozen.status_code == 409, frozen.text
    assert frozen.json()["detail"] == _FROZEN
