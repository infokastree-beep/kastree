"""Clients API integration tests — CRUD, soft-delete archival, mappings."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.archived_record import ArchivedRecord
from app.services.archival import RETENTION_YEARS, add_years, sha256_hex
from app.services.org_provisioning import provision_first_signup
from tests.conftest import auth_headers, make_access_token


@pytest.mark.asyncio
async def test_create_client_defaults_currency_and_materiality(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    response = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": "Acme Trading Ltd", "industry": "Retail"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Acme Trading Ltd"
    assert body["industry"] == "Retail"
    assert body["company_number"] is None
    assert body["functional_currency"] == "GBP"  # org default
    assert Decimal(body["materiality_threshold_pct"]) == Decimal("10.00")
    assert Decimal(body["materiality_threshold_abs"]) == Decimal("1000.00")
    assert body["is_deleted"] is False
    assert body["org_id"] == str(provisioned_org["org_id"])
    assert "id" in body


@pytest.mark.asyncio
async def test_list_clients_pagination_excludes_deleted(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    created_ids: list[str] = []
    for index in range(3):
        resp = await api_client.post(
            "/clients",
            headers=headers,
            json={"name": f"Page Client {index}"},
        )
        assert resp.status_code == 201
        created_ids.append(resp.json()["id"])

    page = await api_client.get("/clients?limit=2&offset=0", headers=headers)
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["total"] >= 3  # includes fixture client from provisioned_org
    assert len(body["items"]) == 2

    # Soft-delete one created client via API then confirm list excludes it
    doomed = created_ids[0]
    deleted = await api_client.delete(f"/clients/{doomed}", headers=headers)
    assert deleted.status_code == 200
    listed = await api_client.get("/clients?limit=100", headers=headers)
    ids = {item["id"] for item in listed.json()["items"]}
    assert doomed not in ids


@pytest.mark.asyncio
async def test_get_client_own_org_ok_other_org_404(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers_a = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        "/clients",
        headers=headers_a,
        json={"name": "Owned Client", "functional_currency": "EUR"},
    )
    assert created.status_code == 201
    client_id = created.json()["id"]

    own = await api_client.get(f"/clients/{client_id}", headers=headers_a)
    assert own.status_code == 200
    assert own.json()["functional_currency"] == "EUR"

    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_other_{suffix}"
    clerk_user_id = f"user_other_{suffix}"
    with SyncSessionLocal() as session:
        other = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name="Other Org",
            clerk_user_id=clerk_user_id,
            email=f"other-{suffix}@example.com",
        )
        session.commit()
        other_org_id = other.organisation.id

    token_b = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=clerk_org_id,
        org_uuid=other_org_id,
    )
    cross = await api_client.get(
        f"/clients/{client_id}",
        headers=auth_headers(token_b),
    )
    assert cross.status_code == 404
    assert cross.status_code != 403

    with SyncSessionLocal() as session:
        set_rls_org_id(session, other_org_id)
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"), {"oid": str(other_org_id)}
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(other_org_id)},
        )
        session.commit()


@pytest.mark.asyncio
async def test_update_client_fields(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": "Before Update"},
    )
    client_id = created.json()["id"]
    updated = await api_client.put(
        f"/clients/{client_id}",
        headers=headers,
        json={
            "name": "After Update",
            "company_number": "123456",
            "materiality_threshold_pct": "12.50",
            "materiality_threshold_abs": "2500.00",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["name"] == "After Update"
    assert body["company_number"] == "123456"
    assert Decimal(body["materiality_threshold_pct"]) == Decimal("12.50")
    assert Decimal(body["materiality_threshold_abs"]) == Decimal("2500.00")


@pytest.mark.asyncio
async def test_soft_delete_writes_archived_record_with_valid_hash(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": "Archive Me", "industry": "Services"},
    )
    assert created.status_code == 201
    client_id = uuid.UUID(created.json()["id"])
    org_id = provisioned_org["org_id"]

    deleted = await api_client.delete(f"/clients/{client_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["is_deleted"] is True
    assert deleted.json()["deleted_at"] is not None

    # Gone from get
    assert (await api_client.get(f"/clients/{client_id}", headers=headers)).status_code == 404

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.scalar(
            select(ArchivedRecord).where(
                ArchivedRecord.entity_type == "client",
                ArchivedRecord.entity_id == client_id,
                ArchivedRecord.archive_reason == "user_deleted",
            )
        )
        assert row is not None
        assert row.client_id == client_id
        assert row.org_id == org_id
        assert row.archived_data["name"] == "Archive Me"
        assert row.archived_data["is_deleted"] is True
        # Valid SHA-256 of archived_data — independently recomputed in the test
        assert len(row.archive_hash) == 64
        independent = hashlib.sha256(
            json.dumps(
                row.archived_data,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        assert row.archive_hash == independent
        assert row.archive_hash == sha256_hex(row.archived_data)
        # Tamper check: wrong payload must not match
        tampered = dict(row.archived_data)
        tampered["name"] = "Tampered"
        assert row.archive_hash != hashlib.sha256(
            json.dumps(
                tampered, sort_keys=True, separators=(",", ":"), default=str
            ).encode()
        ).hexdigest()
        # retention_until ≈ now + 7 years
        today = date.today()
        expected = add_years(today, RETENTION_YEARS)
        assert abs((row.retention_until - expected).days) <= 1


def test_archive_hash_deterministic_across_dict_key_order() -> None:
    """Same snapshot data → same SHA-256 regardless of dict insertion order.

    Independent of sha256_hex: recomputes with hashlib + json.dumps(sort_keys=True).
    """
    snapshot_a = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "org_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "name": "Determinism Co",
        "company_number": None,
        "industry": "Retail",
        "functional_currency": "GBP",
        "materiality_threshold_pct": "10.00",
        "materiality_threshold_abs": "1000.00",
        "is_deleted": True,
        "deleted_at": "2026-08-30T12:00:00+00:00",
        "created_at": "2026-08-01T09:00:00+00:00",
        "updated_at": "2026-08-30T12:00:00+00:00",
    }
    # Different construction / insertion order, same keys and values.
    snapshot_b = {key: snapshot_a[key] for key in reversed(list(snapshot_a.keys()))}
    assert list(snapshot_a.keys()) != list(snapshot_b.keys())

    hash_a = sha256_hex(snapshot_a)
    hash_b = sha256_hex(snapshot_b)
    assert hash_a == hash_b

    independent = hashlib.sha256(
        json.dumps(
            snapshot_a,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    assert hash_a == independent
    # Re-hash snapshot_b the same independent way — still matches.
    independent_b = hashlib.sha256(
        json.dumps(
            snapshot_b,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    assert independent_b == independent


@pytest.mark.asyncio
async def test_soft_delete_rolls_back_when_archive_fails(
    api_client: AsyncClient,
    provisioned_org: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Archive failure must not leave is_deleted=true without an archived_records row."""
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": "Atomic Rollback Client"},
    )
    assert created.status_code == 201
    client_id = created.json()["id"]

    async def _boom(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("simulated archive write failure")

    monkeypatch.setattr(
        "app.routers.clients.archive_client_user_deleted",
        _boom,
    )
    # ASGITransport re-raises unhandled endpoint exceptions (not an HTTP 500 body).
    with pytest.raises(RuntimeError, match="simulated archive write failure"):
        await api_client.delete(f"/clients/{client_id}", headers=headers)

    # Soft-delete rolled back with the failed archive — client still visible.
    got = await api_client.get(f"/clients/{client_id}", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["is_deleted"] is False
    assert got.json()["name"] == "Atomic Rollback Client"

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        archived = session.scalar(
            select(ArchivedRecord).where(
                ArchivedRecord.entity_id == uuid.UUID(client_id),
                ArchivedRecord.entity_type == "client",
            )
        )
        assert archived is None


@pytest.mark.asyncio
async def test_mappings_list_and_bulk_delete(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        "/clients",
        headers=headers,
        json={"name": "Mapping Client"},
    )
    client_id = uuid.UUID(created.json()["id"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add_all(
            [
                AccountMapping(
                    client_id=client_id,
                    source_code="1100",
                    source_name="Cash",
                    canonical_line="cash",
                    confidence=Decimal("1.00"),
                    method="exact",
                    is_confirmed=True,
                ),
                AccountMapping(
                    client_id=client_id,
                    source_code="4100",
                    source_name="Sales",
                    canonical_line="revenue",
                    confidence=Decimal("0.65"),
                    method="code_range",
                    is_confirmed=False,  # excluded from confirmed list
                ),
            ]
        )
        session.commit()

    listed = await api_client.get(f"/clients/{client_id}/mappings", headers=headers)
    assert listed.status_code == 200, listed.text
    mappings = listed.json()["mappings"]
    assert len(mappings) == 1
    assert mappings[0]["source_code"] == "1100"
    assert mappings[0]["is_confirmed"] is True

    wiped = await api_client.delete(f"/clients/{client_id}/mappings", headers=headers)
    assert wiped.status_code == 200, wiped.text
    assert wiped.json()["deleted_count"] == 2  # both rows, confirmed or not

    listed_after = await api_client.get(f"/clients/{client_id}/mappings", headers=headers)
    assert listed_after.json()["mappings"] == []

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        remaining = session.scalars(
            select(AccountMapping).where(AccountMapping.client_id == client_id)
        ).all()
        assert remaining == []
