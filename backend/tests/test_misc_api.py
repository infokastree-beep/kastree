"""API tests for commentary feedback, notifications, and archived records."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.archived_record import ArchivedRecord
from app.models.client import Client
from app.models.notification import Notification
from app.models.trial_balance import TrialBalance
from app.models.user import User
from app.models.variance_analysis import VarianceAnalysis
from app.services.archival import sha256_hex
from app.services.org_provisioning import user_id_for_clerk_user
from tests.conftest import auth_headers, make_access_token


def _seed_variance_with_commentary(
    *,
    org_id: uuid.UUID,
    client_id: uuid.UUID,
    ai_text: str = "Revenue increased due to online sales.",
) -> uuid.UUID:
    tb_id = uuid.uuid4()
    variance_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                client_id=client_id,
                period_end=date(2026, 7, 31),
                file_url=f"/tmp/{tb_id}.xlsx",
                file_type="xlsx",
                status="complete",
                currency="GBP",
            )
        )
        session.flush()
        session.add(
            VarianceAnalysis(
                id=variance_id,
                tb_id=tb_id,
                items={"items": []},
                commentary={
                    "commentaries": {
                        "revenue": {
                            "text": ai_text,
                            "is_ai_generated": True,
                            "is_edited": False,
                            "reasoning": "Material increase",
                            "confidence": "high",
                        }
                    }
                },
                status="complete",
            )
        )
        session.commit()
    return variance_id


def _seed_notification(
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    title: str = "Export ready",
    is_read: bool = False,
) -> uuid.UUID:
    note_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            Notification(
                id=note_id,
                user_id=user_id,
                org_id=org_id,
                type="export_ready",
                title=title,
                message="Your export is ready to download.",
                is_read=is_read,
            )
        )
        session.commit()
    return note_id


def _add_member(*, org_id: uuid.UUID, clerk_org_id: str) -> tuple[uuid.UUID, str]:
    suffix = uuid.uuid4().hex[:10]
    clerk_user_id = f"user_member_{suffix}"
    user_id = user_id_for_clerk_user(clerk_user_id)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            User(
                id=user_id,
                clerk_user_id=clerk_user_id,
                org_id=org_id,
                email=f"member-{suffix}@example.com",
                role="member",
            )
        )
        session.commit()
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        role="member",
        org_uuid=org_id,
    )
    return user_id, token


# --- Commentary feedback ----------------------------------------------------


@pytest.mark.asyncio
async def test_commentary_feedback_thumbs_and_correction_preserves_original(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    headers = auth_headers(provisioned_org["token"])
    ai_text = "Revenue increased due to online sales."
    variance_id = _seed_variance_with_commentary(
        org_id=org_id,
        client_id=provisioned_org["client_id"],
        ai_text=ai_text,
    )

    response = await api_client.post(
        "/commentary/feedback",
        headers=headers,
        json={
            "variance_id": str(variance_id),
            "line_item_code": "revenue",
            "thumbs_up": False,
            "corrected_text": "Revenue rose on stronger e-commerce volume.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["thumbs_up"] is False
    assert body["corrected_text"] == "Revenue rose on stronger e-commerce volume."
    assert body["commentary_updated"] is True

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.get(VarianceAnalysis, variance_id)
        assert row is not None
        commentary = row.commentary["commentaries"]["revenue"]
        assert commentary["text"] == "Revenue rose on stronger e-commerce volume."
        assert commentary["is_edited"] is True
        assert commentary["original_text"] == ai_text
        assert commentary["edited_by_user_id"] == str(provisioned_org["user_id"])


@pytest.mark.asyncio
async def test_commentary_feedback_cross_org_variance_404(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers_a = auth_headers(provisioned_org["token"])
    # Second org
    suffix = uuid.uuid4().hex[:10]
    from app.services.org_provisioning import provision_first_signup

    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=f"org_other_{suffix}",
            org_name=f"Other {suffix}",
            clerk_user_id=f"user_other_{suffix}",
            email=f"other-{suffix}@example.com",
            role="owner",
        )
        set_rls_org_id(session, provisioned.organisation.id)
        other_client = Client(
            org_id=provisioned.organisation.id,
            name="Other Client",
            functional_currency="GBP",
        )
        session.add(other_client)
        session.commit()
        other_org_id = provisioned.organisation.id
        other_client_id = other_client.id
        other_token = make_access_token(
            clerk_user_id=f"user_other_{suffix}",
            clerk_org_id=f"org_other_{suffix}",
            org_uuid=other_org_id,
        )

    variance_id = _seed_variance_with_commentary(
        org_id=other_org_id, client_id=other_client_id
    )
    # Org A cannot feedback on Org B's variance.
    forbidden = await api_client.post(
        "/commentary/feedback",
        headers=headers_a,
        json={
            "variance_id": str(variance_id),
            "line_item_code": "revenue",
            "thumbs_up": True,
        },
    )
    assert forbidden.status_code == 404
    assert forbidden.status_code != 403

    # Cleanup other org lightly
    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        session.execute(text("DELETE FROM commentary_feedback"))
        session.execute(
            text("DELETE FROM variance_analyses WHERE tb_id IN (SELECT id FROM trial_balances)")
        )
        session.execute(text("DELETE FROM trial_balances"))
        session.execute(text("DELETE FROM clients WHERE org_id = :oid"), {"oid": str(other_org_id)})
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(other_org_id)})
        session.execute(text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(other_org_id)})
        session.commit()

    _ = other_token  # silence lint


# --- Notifications ----------------------------------------------------------


@pytest.mark.asyncio
async def test_notifications_list_mark_read_and_read_all(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    user_id = provisioned_org["user_id"]
    headers = auth_headers(provisioned_org["token"])
    n1 = _seed_notification(org_id=org_id, user_id=user_id, title="One")
    n2 = _seed_notification(org_id=org_id, user_id=user_id, title="Two")

    listed = await api_client.get("/notifications", headers=headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] >= 2
    assert all(item["user_id"] == str(user_id) for item in body["items"])

    marked = await api_client.put(f"/notifications/{n1}/read", headers=headers)
    assert marked.status_code == 200, marked.text
    assert marked.json()["is_read"] is True

    all_read = await api_client.put("/notifications/read-all", headers=headers)
    assert all_read.status_code == 200, all_read.text
    assert all_read.json()["updated_count"] >= 1

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        assert session.get(Notification, n1).is_read is True
        assert session.get(Notification, n2).is_read is True


@pytest.mark.asyncio
async def test_notifications_cross_user_404_not_org_leak(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    owner_headers = auth_headers(provisioned_org["token"])
    member_id, member_token = _add_member(
        org_id=org_id, clerk_org_id=provisioned_org["clerk_org_id"]
    )
    member_note = _seed_notification(
        org_id=org_id, user_id=member_id, title="Member only"
    )

    # Owner must not see or mark the member's notification (user_id ownership).
    listed = await api_client.get("/notifications", headers=owner_headers)
    assert listed.status_code == 200
    assert all(item["id"] != str(member_note) for item in listed.json()["items"])

    forbidden = await api_client.put(
        f"/notifications/{member_note}/read",
        headers=owner_headers,
    )
    assert forbidden.status_code == 404
    assert forbidden.status_code != 403

    # Member can mark their own.
    ok = await api_client.put(
        f"/notifications/{member_note}/read",
        headers=auth_headers(member_token),
    )
    assert ok.status_code == 200


# --- Archived records -------------------------------------------------------


@pytest.mark.asyncio
async def test_archived_records_list_and_hash_verified_true(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    # Soft-delete creates archived_records via clients router.
    deleted = await api_client.delete(
        f"/clients/{provisioned_org['client_id']}",
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text

    listed = await api_client.get(
        f"/clients/{provisioned_org['client_id']}/archived-records",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) >= 1
    record_id = items[0]["id"]

    detail = await api_client.get(f"/archived-records/{record_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["hash_verified"] is True
    assert body["archive_hash"] == sha256_hex(body["archived_data"])


@pytest.mark.asyncio
async def test_archived_records_hash_verified_false_when_data_corrupted(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    headers = auth_headers(provisioned_org["token"])
    deleted = await api_client.delete(
        f"/clients/{provisioned_org['client_id']}",
        headers=headers,
    )
    assert deleted.status_code == 200, deleted.text

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            select(ArchivedRecord).where(ArchivedRecord.org_id == org_id)
        ).scalar_one()
        record_id = row.id
        # Tamper with snapshot without updating archive_hash.
        data = dict(row.archived_data)
        data["name"] = "TAMPERED NAME"
        row.archived_data = data
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(row, "archived_data")
        session.commit()

    detail = await api_client.get(f"/archived-records/{record_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["hash_verified"] is False
    assert detail.json()["hash_verified"] is not True


@pytest.mark.asyncio
async def test_archived_records_cross_org_404(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    await api_client.delete(
        f"/clients/{provisioned_org['client_id']}",
        headers=headers,
    )
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        record_id = session.execute(
            select(ArchivedRecord.id).where(
                ArchivedRecord.org_id == provisioned_org["org_id"]
            )
        ).scalar_one()

    # Foreign org token
    suffix = uuid.uuid4().hex[:10]
    from app.services.org_provisioning import provision_first_signup

    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=f"org_arc_{suffix}",
            org_name="Arc Other",
            clerk_user_id=f"user_arc_{suffix}",
            email=f"arc-{suffix}@example.com",
            role="owner",
        )
        session.commit()
        other_token = make_access_token(
            clerk_user_id=f"user_arc_{suffix}",
            clerk_org_id=f"org_arc_{suffix}",
            org_uuid=other.organisation.id,
        )
        other_org_id = other.organisation.id

    cross = await api_client.get(
        f"/archived-records/{record_id}",
        headers=auth_headers(other_token),
    )
    assert cross.status_code == 404

    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        session.execute(text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(other_org_id)})
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"), {"oid": str(other_org_id)}
        )
        session.commit()


@pytest.mark.asyncio
async def test_org_level_archived_records_owner_only(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    headers = auth_headers(provisioned_org["token"])
    record_id = uuid.uuid4()
    snapshot = {"kind": "org", "note": "cancelled"}
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            ArchivedRecord(
                id=record_id,
                org_id=org_id,
                client_id=None,
                entity_type="organisation",
                entity_id=org_id,
                archive_reason="subscription_cancelled",
                archived_by_user_id=provisioned_org["user_id"],
                archived_data=snapshot,
                archive_hash=sha256_hex(snapshot),
                retention_until=date(2033, 1, 1),
            )
        )
        session.commit()

    listed = await api_client.get(
        "/organisations/me/archived-records",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == str(record_id) for item in listed.json()["items"])

    _, member_token = _add_member(
        org_id=org_id, clerk_org_id=provisioned_org["clerk_org_id"]
    )
    forbidden = await api_client.get(
        "/organisations/me/archived-records",
        headers=auth_headers(member_token),
    )
    assert forbidden.status_code == 403
