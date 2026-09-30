"""Role matrix: writes follow users.role on every request, including mid-session demotion."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.user import User
from tests.conftest import auth_headers, balanced_tb_xlsx_bytes, make_access_token
from tests.test_organisations_api import _add_org_user

_FORBIDDEN = "You don't have permission to access this resource."


def _set_role(*, org_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        user = session.get(User, user_id)
        assert user is not None
        user.role = role
        session.commit()


def _upload_files() -> dict:
    return {
        "file": (
            "tb.xlsx",
            balanced_tb_xlsx_bytes(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }


@pytest.mark.asyncio
async def test_demote_to_viewer_rejects_upload_export_and_statements(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Same bearer token: member may upload; after demotion the viewer may not.

    The JWT role claim stays ``owner`` for the whole test. Authorisation reads
    ``users.role``, matching invites.
    """
    org_id = provisioned_org["org_id"]
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="demote",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=org_id,
    )
    headers = auth_headers(token)

    me = await api_client.get("/users/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "member"

    upload = await api_client.post(
        "/trial-balances/upload",
        headers=headers,
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_end": "2026-03-31",
            "currency": "GBP",
        },
        files=_upload_files(),
    )
    assert upload.status_code == 202, upload.text

    _set_role(org_id=org_id, user_id=user_id, role="viewer")

    me_after = await api_client.get("/users/me", headers=headers)
    assert me_after.status_code == 200, me_after.text
    assert me_after.json()["role"] == "viewer"

    readable = await api_client.get("/organisations/me", headers=headers)
    assert readable.status_code == 200, readable.text

    unknown_tb = uuid.uuid4()
    rejected = {
        "upload": await api_client.post(
            "/trial-balances/upload",
            headers=headers,
            data={
                "company_id": str(provisioned_org["company_id"]),
                "period_end": "2026-04-30",
                "currency": "GBP",
            },
            files=_upload_files(),
        ),
        "statements": await api_client.post(
            f"/trial-balances/{unknown_tb}/statements",
            headers=headers,
        ),
        "export": await api_client.post(
            f"/trial-balances/{unknown_tb}/export",
            headers=headers,
            json={"format": "pdf"},
        ),
        "invite": await api_client.post(
            "/organisations/me/invites",
            headers=headers,
            json={"email": "blocked@example.com", "role": "member"},
        ),
    }
    for name, response in rejected.items():
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"
        assert response.json()["detail"] == _FORBIDDEN
