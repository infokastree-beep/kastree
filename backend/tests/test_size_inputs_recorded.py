"""Stored size inputs for the fictional first-period company."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from tests.conftest import auth_headers, make_access_token
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_tb_ingestion import _year_end

_FORBIDDEN = "You don't have permission to access this resource."
_CURRENT = {
    "turnover": "100000.00",
    "balance_sheet_total": "35000.00",
    "employees": 677,
}


@pytest.mark.asyncio
async def test_qa_company_size_inputs_are_stored_without_amounts_in_the_audit(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    currency = await api_client.put(
        f"/companies/{provisioned_org['company_id']}",
        headers=auth_headers(provisioned_org["token"]),
        json={"functional_currency": "EUR", "acknowledge_currency_change": True},
    )
    assert currency.status_code == 200, currency.text
    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="size-member",
    )
    member = auth_headers(
        make_access_token(
            clerk_user_id=clerk_user_id,
            clerk_org_id=provisioned_org["clerk_org_id"],
            role="member",
            org_uuid=provisioned_org["org_id"],
        )
    )
    marked = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=member,
    )
    assert marked.status_code == 200, marked.text
    recorded = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=member,
        json={"current": _CURRENT},
    )
    assert recorded.status_code == 200, recorded.text
    body = recorded.json()
    assert body["eligible"] is True
    assert body["current_conditions_met"] == 2
    assert body["preceding_conditions_met"] is None
    assert body["size_current_turnover"] == "100000.00"
    assert body["size_current_balance_sheet"] == "35000.00"
    assert body["size_current_employees"] == 677
    assert body["size_preceding_turnover"] is None
    assert body["size_preceding_balance_sheet"] is None
    assert body["size_preceding_employees"] is None
    message = body["message"]
    assert message == (
        "Current year: turnover met; balance sheet total met; employees not met. "
        "This year end is a first financial period, so there is no preceding year. "
        "A reviewer must confirm whether the audit exemption is available "
        "(two of three versus all conditions)."
    )
    assert "eligible" not in message.casefold()

    year_end = await api_client.get(f"/year-ends/{year_end_id}", headers=member)
    assert year_end.status_code == 200, year_end.text
    stored = year_end.json()
    assert stored["size_current_turnover"] == "100000.00"
    assert stored["size_current_balance_sheet"] == "35000.00"
    assert stored["size_current_employees"] == 677
    assert stored["size_preceding_employees"] is None
    assert stored["size_message"] == message

    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/size-eligibility",
        headers=member,
        json={"current": _CURRENT},
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        row = session.execute(
            text(
                """
                SELECT old_value, new_value
                FROM audit_logs
                WHERE org_id = :org AND action = 'size_eligibility_recorded'
                """
            ),
            {"org": str(provisioned_org["org_id"])},
        ).one()
    assert row.old_value is None
    logged = json.dumps(row.new_value)
    assert row.new_value["eligible"] is True
    assert row.new_value["current_conditions_met"] == 2
    assert row.new_value["current_employees"] == 677
    assert row.new_value["preceding_employees"] is None
    assert row.new_value["confirmed"] is True
    assert "100000" not in logged
    assert "35000" not in logged
    assert "turnover" not in row.new_value
    assert "balance_sheet" not in row.new_value
