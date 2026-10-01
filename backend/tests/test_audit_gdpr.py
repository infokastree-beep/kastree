"""Week 12 append-only audit log, escaped CSV, and erasure that keeps records."""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import AsyncSessionLocal, SyncSessionLocal, aset_rls_org_id
from app.services.archival import verify_archive_hash
from app.services.audit import append_audit_log, load_audit_log, verify_audit_chain
from app.services.retention import (
    REDACTED_CLIENT_NAME,
    RETENTION_POLICY_STATEMENT,
)
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role

_FORBIDDEN = "You don't have permission to access this resource."


async def _append_formula_rows(org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as session:
        await aset_rls_org_id(session, org_id)
        for action in ("=SUM(A1)", "+cmd", "-item", "@name", "Cash"):
            await append_audit_log(
                session,
                org_id=org_id,
                user_id=user_id,
                action=action,
                entity_type="client",
                entity_id=org_id,
                new_value={"note": action},
            )
        await session.commit()


@pytest.mark.asyncio
async def test_audit_chain_and_csv_escape_formula_leads(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    await _append_formula_rows(provisioned_org["org_id"], provisioned_org["user_id"])
    headers = auth_headers(provisioned_org["token"])
    chain = await api_client.get("/audit-logs", headers=headers)
    assert chain.status_code == 200, chain.text
    assert chain.json()["count"] == 5
    assert chain.json()["chain_valid"] is True
    exported = await api_client.get("/audit-logs/export.csv", headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("text/csv")
    assert 'filename="audit-log.csv"' in exported.headers["content-disposition"]
    assert exported.headers["x-audit-chain-valid"] == "true"
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    actions = [row["action"] for row in rows]
    assert actions == ["'=SUM(A1)", "'+cmd", "'-item", "'@name", "Cash"]
    assert rows[0]["prev_hash"] == "0" * 64
    assert rows[1]["prev_hash"] == rows[0]["row_hash"]

    policy = await api_client.get("/audit-logs/policy", headers=headers)
    assert policy.status_code == 200, policy.text
    body = policy.json()
    assert body["statutory_floor_years"] == 6
    assert body["retention_years"] == 7
    assert body["buffer_is_statutory"] is False
    assert body["statement"] == RETENTION_POLICY_STATEMENT
    assert "not a statutory requirement" in body["statement"]
    assert "audit log is append-only" in body["statement"]
    assert "archived_records" in body["erasure_retains"]


@pytest.mark.asyncio
async def test_tampered_audit_row_breaks_the_chain(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    await _append_formula_rows(provisioned_org["org_id"], provisioned_org["user_id"])
    with SyncSessionLocal() as session:
        session.execute(
            text(
                "ALTER TABLE audit_logs DISABLE TRIGGER findraft_audit_log_append_only"
            )
        )
        session.execute(
            text(
                "UPDATE audit_logs SET action = 'tampered' "
                "WHERE org_id = :org AND chain_seq = 1"
            ),
            {"org": str(provisioned_org["org_id"])},
        )
        session.execute(
            text("ALTER TABLE audit_logs ENABLE TRIGGER findraft_audit_log_append_only")
        )
        session.commit()
    async with AsyncSessionLocal() as session:
        rows = await load_audit_log(session, org_id=provisioned_org["org_id"])
    assert verify_audit_chain(rows) is False
    exported = await api_client.get(
        "/audit-logs/export.csv",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert exported.status_code == 200, exported.text
    assert exported.headers["x-audit-chain-valid"] == "false"


@pytest.mark.asyncio
async def test_client_erasure_keeps_archive_and_company(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    client_id = str(provisioned_org["client_id"])
    with SyncSessionLocal() as session:
        original = session.execute(
            text("SELECT name FROM clients WHERE id = :id"),
            {"id": client_id},
        ).scalar_one()
        company = session.execute(
            text("SELECT name FROM companies WHERE id = :id"),
            {"id": str(provisioned_org["company_id"])},
        ).scalar_one()
    removed = await api_client.delete(f"/clients/{client_id}", headers=headers)
    assert removed.status_code == 200, removed.text
    erased = await api_client.post(f"/clients/{client_id}/erasure", headers=headers)
    assert erased.status_code == 200, erased.text
    assert erased.json()["erased"] is True
    assert erased.json()["statement"] == RETENTION_POLICY_STATEMENT
    assert original not in erased.json()["statement"]
    again = await api_client.post(f"/clients/{client_id}/erasure", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["erased"] is False
    with SyncSessionLocal() as session:
        live = session.execute(
            text("SELECT name FROM clients WHERE id = :id"),
            {"id": client_id},
        ).scalar_one()
        company_after = session.execute(
            text("SELECT name FROM companies WHERE id = :id"),
            {"id": str(provisioned_org["company_id"])},
        ).scalar_one()
        company_count = session.execute(
            text("SELECT count(*) FROM companies WHERE client_id = :id"),
            {"id": client_id},
        ).scalar_one()
        archive = session.execute(
            text(
                "SELECT archived_data, archive_hash FROM archived_records "
                "WHERE client_id = :id AND entity_type = 'client'"
            ),
            {"id": client_id},
        ).one()
        audit_count = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE org_id = :org "
                "AND action = 'erasure'"
            ),
            {"org": str(provisioned_org["org_id"])},
        ).scalar_one()
        leaked = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE org_id = :org AND ("
                "coalesce(old_value::text, '') LIKE :name OR "
                "coalesce(new_value::text, '') LIKE :name)"
            ),
            {"org": str(provisioned_org["org_id"]), "name": f"%{original}%"},
        ).scalar_one()
    assert live == REDACTED_CLIENT_NAME
    assert company_after == company
    assert company_count == 1
    assert archive.archived_data["name"] == original
    assert verify_archive_hash(archive.archived_data, archive.archive_hash) is True
    assert audit_count == 1
    assert leaked == 0


@pytest.mark.asyncio
async def test_user_erasure_keeps_the_row_and_refuses_the_last_owner(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    member_id, member_clerk, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="week12-member",
    )
    with SyncSessionLocal() as session:
        original_email = session.execute(
            text("SELECT email FROM users WHERE id = :id"),
            {"id": str(member_id)},
        ).scalar_one()
    erased = await api_client.post(f"/users/{member_id}/erasure", headers=headers)
    assert erased.status_code == 200, erased.text
    assert erased.json()["erased"] is True
    assert original_email not in erased.text
    again = await api_client.post(f"/users/{member_id}/erasure", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["erased"] is False
    with SyncSessionLocal() as session:
        row = session.execute(
            text("SELECT email, clerk_user_id FROM users WHERE id = :id"),
            {"id": str(member_id)},
        ).one()
        audit_count = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE org_id = :org "
                "AND entity_type = 'user'"
            ),
            {"org": str(provisioned_org["org_id"])},
        ).scalar_one()
        leaked = session.execute(
            text(
                "SELECT count(*) FROM audit_logs WHERE org_id = :org AND "
                "coalesce(new_value::text, '') LIKE :email"
            ),
            {"org": str(provisioned_org["org_id"]), "email": f"%{original_email}%"},
        ).scalar_one()
    assert row.email == f"erased-{member_id}@erased.invalid"
    assert row.clerk_user_id == f"erased-{member_id}"
    assert row.clerk_user_id != member_clerk
    assert audit_count == 1
    assert leaked == 0

    refused = await api_client.post(
        f"/users/{provisioned_org['user_id']}/erasure",
        headers=headers,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == "The last owner cannot be erased"

    admin_id, admin_clerk, _admin_issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="admin",
        email_prefix="week12-admin",
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=admin_id, role="admin")
    admin_headers = auth_headers(
        make_access_token(
            clerk_user_id=admin_clerk,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="owner",
            org_uuid=provisioned_org["org_id"],
        )
    )
    blocked = await api_client.post(
        f"/users/{provisioned_org['user_id']}/erasure",
        headers=admin_headers,
    )
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == _FORBIDDEN


@pytest.mark.asyncio
async def test_viewer_cannot_export_the_audit_log(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="week12-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    viewer = auth_headers(token)
    policy = await api_client.get("/audit-logs/policy", headers=viewer)
    assert policy.status_code == 200, policy.text
    chain = await api_client.get("/audit-logs", headers=viewer)
    assert chain.status_code == 403
    assert chain.json()["detail"] == _FORBIDDEN
    exported = await api_client.get("/audit-logs/export.csv", headers=viewer)
    assert exported.status_code == 403
    assert exported.json()["detail"] == _FORBIDDEN
    erased = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/erasure",
        headers=viewer,
    )
    assert erased.status_code == 403
    missing = await api_client.post(
        f"/clients/{uuid.uuid4()}/erasure",
        headers=auth_headers(provisioned_org["token"]),
    )
    assert missing.status_code == 404
