"""Shared pytest fixtures — real Postgres, JWT helpers, ASGI client."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta, timezone
from io import BytesIO

import jwt
import openpyxl
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import settings
from app.db import SyncSessionLocal, set_rls_org_id
from app.main import app
from app.models.client import Client
from app.models.company import Company
from app.services.org_provisioning import (
    organisation_id_for_clerk_org,
    provision_first_signup,
)


@pytest.fixture(scope="session", autouse=True)
def _force_rls_on_all_tables() -> None:
    """Ensure FORCE ROW LEVEL SECURITY is on (migration a1b2c3d4e5f6)."""
    tables = (
        "clients",
        "audit_logs",
        "notifications",
        "archived_records",
        "users",
        "subscription_events",
        "organisations",
        "companies",
        "trial_balances",
        "account_mappings",
        "financial_statements",
        "variance_analyses",
        "risk_flags",
        "exports",
        "processing_jobs",
        "statement_line_items",
        "commentary_feedback",
    )
    with SyncSessionLocal() as session:
        for table in tables:
            session.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        session.commit()


@pytest.fixture(autouse=True)
def _patch_request_auth_to_test_hs256(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route request auth through HS256 test tokens for the ASGI suite only.

    Production ``decode_access_token`` is RS256/Clerk JWKS only. Tests mint
    HS256 tokens via ``make_access_token`` and swap the entry point here so
    ``get_auth_context`` never needs a live JWKS. This patch does not exist
    outside pytest.
    """
    from app.dependencies import decode_test_hs256_token

    monkeypatch.setattr(
        "app.dependencies.decode_access_token",
        decode_test_hs256_token,
    )


def make_access_token(
    *,
    clerk_user_id: str,
    clerk_org_id: str,
    role: str = "owner",
    org_uuid: uuid.UUID | None = None,
) -> str:
    org_id = org_uuid or organisation_id_for_clerk_org(clerk_org_id)
    payload = {
        "sub": clerk_user_id,
        "org_id": clerk_org_id,
        "org_uuid": str(org_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(
        payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm
    )


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def balanced_tb_xlsx_bytes() -> bytes:
    """Closed-books TB that passes tb_integrity, balance_sheet_balance, and net_assets."""
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.append(["Account Code", "Account Name", "Debit", "Credit"])
    ws.append(["1100", "Cash at bank", "10000.00", "0.00"])
    ws.append(["3100", "Retained earnings", "0.00", "6000.00"])
    ws.append(["3000", "Share capital", "0.00", "4000.00"])
    # P&L lines that net to zero so SOPL is non-empty but BS still balances.
    ws.append(["4100", "Sales - Online", "0.00", "5000.00"])
    ws.append(["6100", "Operating expenses", "5000.00", "0.00"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture
def provisioned_org() -> Iterator[dict]:
    """Create org+owner via the real RLS bootstrap; yield ids; clean up after."""
    suffix = uuid.uuid4().hex[:10]
    clerk_org_id = f"org_test_{suffix}"
    clerk_user_id = f"user_test_{suffix}"
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=clerk_org_id,
            org_name=f"Test Org {suffix}",
            clerk_user_id=clerk_user_id,
            email=f"owner-{suffix}@example.com",
            role="owner",
        )
        set_rls_org_id(session, provisioned.organisation.id)
        client = Client(
            org_id=provisioned.organisation.id,
            name=f"Client {suffix}",
        )
        session.add(client)
        session.flush()
        company = Company(
            client_id=client.id,
            name=f"Company {suffix}",
            functional_currency="GBP",
        )
        session.add(company)
        session.commit()
        data = {
            "org_id": provisioned.organisation.id,
            "user_id": provisioned.user.id,
            "client_id": client.id,
            "company_id": company.id,
            "clerk_org_id": clerk_org_id,
            "clerk_user_id": clerk_user_id,
            "token": make_access_token(
                clerk_user_id=clerk_user_id,
                clerk_org_id=clerk_org_id,
                org_uuid=provisioned.organisation.id,
            ),
        }
    yield data
    with SyncSessionLocal() as session:
        set_rls_org_id(session, data["org_id"])
        session.execute(
            text(
                "DELETE FROM statement_line_items WHERE statement_id IN "
                "(SELECT id FROM financial_statements WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM financial_statements WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM commentary_feedback WHERE variance_id IN "
                "(SELECT id FROM variance_analyses WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM variance_analyses WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM risk_flags WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM exports WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM processing_jobs WHERE tb_id IN "
                "(SELECT id FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM account_mappings WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM archived_records WHERE org_id = :oid"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM trial_balances WHERE company_id IN "
                "(SELECT id FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid))"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text(
                "DELETE FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)"
            ),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM clients WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM notifications WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM subscription_events WHERE org_id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": str(data["org_id"])},
        )
        session.commit()


@pytest_asyncio.fixture
async def api_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
