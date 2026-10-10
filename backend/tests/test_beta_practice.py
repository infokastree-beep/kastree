"""Week 13: the first practice records the beta gate, and the golden suite is green."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.services.beta import BETA_STATEMENT
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from tests.conftest import auth_headers, make_access_token
from tests.test_draft_locking import _answer_disclosures, _draft_path
from tests.test_organisations_api import _add_org_user
from tests.test_role_enforcement import _set_role
from tests.test_statutory_statements import _ready_golden, _statements_path
from tests.test_tb_ingestion import _year_end

_FORBIDDEN = "You don't have permission to access this resource."
_ENGINE_ROOT = Path(__file__).resolve().parents[2] / "findraft"


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


@pytest.mark.asyncio
async def test_beta_position_stays_unsigned_and_acknowledgement_is_once(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    position = await api_client.get("/beta", headers=headers)
    assert position.status_code == 200, position.text
    body = position.json()
    assert body["pack_id"] == "frs102-1a-ie"
    assert body["wording_signed_off"] is False
    assert body["self_review_required"] is True
    assert body["filing_included"] is False
    assert body["acknowledged"] is False
    assert body["statement"] == BETA_STATEMENT
    assert "not signed off" in body["statement"]
    assert "does not file" in body["statement"]
    assert "iXBRL" in body["statement"]
    assert "not in this beta" in body["statement"]

    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="week13-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    viewer = auth_headers(token)
    readable = await api_client.get("/beta", headers=viewer)
    assert readable.status_code == 200, readable.text
    assert readable.json()["acknowledged"] is False
    refused = await api_client.post("/beta/acknowledgement", headers=viewer)
    assert refused.status_code == 403
    assert refused.json()["detail"] == _FORBIDDEN

    recorded = await api_client.post("/beta/acknowledgement", headers=headers)
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["recorded"] is True
    assert recorded.json()["acknowledged"] is True
    assert recorded.json()["wording_signed_off"] is False
    assert recorded.json()["filing_included"] is False
    assert recorded.json()["statement"] == BETA_STATEMENT
    again = await api_client.post("/beta/acknowledgement", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["recorded"] is False
    assert again.json()["wording_signed_off"] is False

    after = await api_client.get("/beta", headers=viewer)
    assert after.status_code == 200, after.text
    assert after.json()["acknowledged"] is True
    assert after.json()["wording_signed_off"] is False

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        rows = session.execute(
            text(
                "SELECT new_value FROM audit_logs WHERE org_id = :org "
                "AND action = 'beta_self_review'"
            ),
            {"org": str(provisioned_org["org_id"])},
        ).all()
    assert len(rows) == 1
    stored = rows[0].new_value
    assert stored["wording_signed_off"] is False
    assert stored["filing_included"] is False
    assert stored["pack_id"] == "frs102-1a-ie"
    assert stored["source"] == "practice"
    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        columns = session.execute(
            text(
                "SELECT product2_acknowledged_at, product2_acknowledged_by_user_id "
                "FROM organisations WHERE id = :org"
            ),
            {"org": str(provisioned_org["org_id"])},
        ).one()
    assert columns.product2_acknowledged_at is not None
    assert columns.product2_acknowledged_by_user_id == provisioned_org["user_id"]
    chain = await api_client.get("/audit-logs", headers=headers)
    assert chain.status_code == 200, chain.text
    assert chain.json()["chain_valid"] is True


@pytest.mark.asyncio
async def test_first_practice_golden_final_keeps_the_engine_figures(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    headers = auth_headers(provisioned_org["token"])
    recorded = await api_client.post("/beta/acknowledgement", headers=headers)
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["recorded"] is True

    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    statements = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["watermark"] == "DRAFT"
    assert statements.json()["net_assets"] == "455812.00"
    assert statements.json()["profit"] == "157650.00"

    reconciliation = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
        headers=headers,
    )
    assert reconciliation.status_code == 200, reconciliation.text
    codes = {item["code"] for item in reconciliation.json()["checks"]}
    assert "V-BANK-001" not in codes
    balance = next(
        item for item in reconciliation.json()["checks"] if item["code"] == "V-BS-001"
    )
    assert balance["passed"] is True

    version = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}",
        headers=headers,
    )
    assert version.status_code == 200, version.text
    draft_id = version.json()["draft_id"]
    row_version = await _answer_disclosures(
        api_client, headers, year_end_id, draft_id, 1
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
    final = await api_client.post(
        _draft_path(year_end_id, draft_id, "finalise"),
        headers={**headers, "Idempotency-Key": "week13-final"},
        json={"row_version": row_version},
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "final"
    assert final.json()["pack_id"] == "frs102-1a-ie"

    frozen = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["watermark"] == "FINAL"
    assert frozen.json()["net_assets"] == "455812.00"
    assert frozen.json()["profit"] == "157650.00"
    pdf = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}.pdf", headers=headers
    )
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")
    assert (
        'filename="statutory-statements-final.pdf"'
        in pdf.headers["content-disposition"]
    )
    evidence = await api_client.get(
        f"{_statements_path(year_end_id, version_id)}/evidence",
        headers=headers,
    )
    assert evidence.status_code == 200, evidence.text
    assert [document["role"] for document in evidence.json()["documents"]] == [
        "trial_balance"
    ]


def _backfill_sql() -> str:
    source = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "k7l8m9n0o1_product2_acknowledgement.py"
    ).read_text()
    start = source.index('BACKFILL_SQL = """') + len('BACKFILL_SQL = """')
    end = source.index('"""', start)
    return source[start:end]


@pytest.mark.asyncio
async def test_acknowledgement_columns_follow_the_earliest_audit_row(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """A cleared practice is restored from the earliest beta_self_review row.

    A timestamp that is already set is left alone. An audit row with the
    columns cleared does not count as acknowledged.
    """
    headers = auth_headers(provisioned_org["token"])
    recorded = await api_client.post("/beta/acknowledgement", headers=headers)
    assert recorded.status_code == 200, recorded.text
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        earliest = session.execute(
            text(
                "SELECT created_at, user_id FROM audit_logs "
                "WHERE org_id = :org AND action = 'beta_self_review' "
                "ORDER BY created_at ASC, chain_seq ASC LIMIT 1"
            ),
            {"org": str(org_id)},
        ).one()
        session.execute(
            text(
                "UPDATE organisations SET product2_acknowledged_at = NULL, "
                "product2_acknowledged_by_user_id = NULL WHERE id = :org"
            ),
            {"org": str(org_id)},
        )
        session.commit()

    cleared = await api_client.get("/beta", headers=headers)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["acknowledged"] is False

    again = await api_client.post("/beta/acknowledgement", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["recorded"] is True

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE organisations "
                "SET product2_acknowledged_at = TIMESTAMPTZ '2000-01-01 00:00:00+00', "
                "product2_acknowledged_by_user_id = NULL "
                "WHERE id = :org"
            ),
            {"org": str(org_id)},
        )
        session.execute(text(_backfill_sql()))
        kept = session.execute(
            text(
                "SELECT product2_acknowledged_at FROM organisations WHERE id = :org"
            ),
            {"org": str(org_id)},
        ).scalar_one()
        assert kept.isoformat().startswith("2000-01-01")
        session.execute(
            text(
                "UPDATE organisations SET product2_acknowledged_at = NULL, "
                "product2_acknowledged_by_user_id = NULL WHERE id = :org"
            ),
            {"org": str(org_id)},
        )
        session.execute(text(_backfill_sql()))
        restored = session.execute(
            text(
                "SELECT product2_acknowledged_at, product2_acknowledged_by_user_id "
                "FROM organisations WHERE id = :org"
            ),
            {"org": str(org_id)},
        ).one()
        session.commit()
    assert restored.product2_acknowledged_at == earliest.created_at
    assert restored.product2_acknowledged_by_user_id == earliest.user_id

    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "k7l8m9n0o1_product2_acknowledgement.py"
    ).read_text()
    assert "rolsuper OR rolbypassrls" in migration
    assert "GRANT ALL ON" not in migration
    assert "GRANT ALL PRIVILEGES" not in migration


def test_engine_golden_suite_is_green() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=_ENGINE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "OK" in completed.stderr
