"""Mapping confirm API — override of prior tier suggestions must persist."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.processing_job import ProcessingJob
from app.models.trial_balance import TrialBalance
from app.services.mapper import EXACT_CONFIDENCE, MappingResult
from app.services.tb_pipeline import _persist_mapping_results
from tests.conftest import auth_headers


def _seed_tb_with_code_range_mapping(
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """TB with 7000 (code_range → depreciation) and 4000 (unmapped). Returns tb_id, mapping_id."""
    tb_id = uuid.uuid4()
    mapping_7000_id = uuid.uuid4()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                company_id=company_id,
                period_end=date(2026, 7, 31),
                file_url=f"file:///tmp/{tb_id}.xlsx",
                file_type="xlsx",
                status="mapping",
                currency="GBP",
                parsed_data={
                    "rows": [
                        {
                            "account_code": "4000",
                            "account_name": "Sales Revenue",
                            "debit": "0",
                            "credit": "10000.00",
                            "net_balance": "-10000.00",
                            "currency": "GBP",
                            "row_index": 1,
                        },
                        {
                            "account_code": "7000",
                            "account_name": "Interest Expense",
                            "debit": "500.00",
                            "credit": "0",
                            "net_balance": "500.00",
                            "currency": "GBP",
                            "row_index": 2,
                        },
                    ]
                },
            )
        )
        session.add(
            AccountMapping(
                id=mapping_7000_id,
                company_id=company_id,
                source_code="7000",
                source_name="Interest Expense",
                canonical_line="depreciation",
                confidence=Decimal("0.65"),
                method="code_range",
                is_confirmed=False,
            )
        )
        session.add(
            AccountMapping(
                company_id=company_id,
                source_code="4000",
                source_name="Sales Revenue",
                canonical_line="unmapped",
                confidence=None,
                method="llm",
                is_confirmed=False,
            )
        )
        session.commit()
    return tb_id, mapping_7000_id


@pytest.mark.asyncio
async def test_confirm_overrides_code_range_suggestion(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """User override of a Tier-3 code_range row must replace the heuristic guess."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])
    tb_id, mapping_7000_id = _seed_tb_with_code_range_mapping(
        org_id=org_id,
        company_id=company_id,
    )

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        mapping_4000 = session.scalar(
            select(AccountMapping).where(
                AccountMapping.company_id == company_id,
                AccountMapping.source_code == "4000",
            )
        )
        assert mapping_4000 is not None

    confirm = await api_client.post(
        f"/trial-balances/{tb_id}/mapping/confirm",
        json={
            "mappings": [
                {
                    "id": str(mapping_4000.id),
                    "canonical_line": "revenue",
                    "is_confirmed": True,
                    "is_ignored": False,
                },
                {
                    "id": str(mapping_7000_id),
                    "canonical_line": "interest_expense",
                    "is_confirmed": True,
                    "is_ignored": False,
                },
            ]
        },
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["confirmed_count"] == 2

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row_7000 = session.get(AccountMapping, mapping_7000_id)
        assert row_7000 is not None
        assert row_7000.canonical_line == "interest_expense"
        assert row_7000.is_confirmed is True
        assert row_7000.method == "manual"
        assert row_7000.confidence == Decimal("1.00")

        row_4000 = session.get(AccountMapping, mapping_4000.id)
        assert row_4000 is not None
        assert row_4000.canonical_line == "revenue"
        assert row_4000.is_confirmed is True
        assert row_4000.method == "manual"
        assert row_4000.confidence == Decimal("1.00")


@pytest.mark.asyncio
async def test_confirm_rejects_unmapped_canonical_line(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Explicit confirm must not accept canonical_line=unmapped."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])
    tb_id, mapping_7000_id = _seed_tb_with_code_range_mapping(
        org_id=org_id,
        company_id=company_id,
    )

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        mapping_4000 = session.scalar(
            select(AccountMapping).where(
                AccountMapping.company_id == company_id,
                AccountMapping.source_code == "4000",
            )
        )
        assert mapping_4000 is not None

    response = await api_client.post(
        f"/trial-balances/{tb_id}/mapping/confirm",
        json={
            "mappings": [
                {
                    "id": str(mapping_7000_id),
                    "canonical_line": "interest_expense",
                    "is_confirmed": True,
                    "is_ignored": False,
                },
                {
                    "id": str(mapping_4000.id),
                    "canonical_line": "unmapped",
                    "is_confirmed": True,
                    "is_ignored": False,
                },
            ]
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert "unmapped" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_confirm_empty_mappings_list_rejected(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Empty mappings[] must not hit the legacy confirm-without-overrides path."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])
    tb_id, _ = _seed_tb_with_code_range_mapping(org_id=org_id, company_id=company_id)

    response = await api_client.post(
        f"/trial-balances/{tb_id}/mapping/confirm",
        json={"mappings": []},
        headers=headers,
    )
    assert response.status_code == 400

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.scalar(
            select(AccountMapping).where(
                AccountMapping.company_id == company_id,
                AccountMapping.source_code == "7000",
            )
        )
        assert row is not None
        assert row.canonical_line == "depreciation"
        assert row.is_confirmed is False
        assert (
            session.scalar(
                select(ProcessingJob).where(
                    ProcessingJob.tb_id == tb_id,
                    ProcessingJob.job_type == "validate",
                )
            )
            is None
        )


@pytest.mark.asyncio
async def test_confirmed_confidence_survives_reupload(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Human-confirmed confidence must stay 1.00 after a later map job skips the row."""
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    headers = auth_headers(provisioned_org["token"])
    tb_id, mapping_7000_id = _seed_tb_with_code_range_mapping(
        org_id=org_id,
        company_id=company_id,
    )

    confirm = await api_client.post(
        f"/trial-balances/{tb_id}/mapping/confirm",
        json={
            "mappings": [
                {
                    "id": str(mapping_7000_id),
                    "canonical_line": "interest_expense",
                    "is_confirmed": True,
                    "is_ignored": False,
                },
            ]
        },
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.get(AccountMapping, mapping_7000_id)
        assert row is not None
        assert row.method == "manual"
        assert row.confidence == Decimal("1.00")

        # Simulate a subsequent upload where Tier 1 would produce exact/1.00.
        _persist_mapping_results(
            session,
            company_id=company_id,
            results=[
                MappingResult(
                    source_code="7000",
                    source_name="Interest Expense",
                    canonical_line="interest_expense",
                    confidence=EXACT_CONFIDENCE,
                    method="exact",
                )
            ],
        )
        session.commit()

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row_after_reupload = session.scalar(
            select(AccountMapping).where(AccountMapping.id == mapping_7000_id)
        )
        assert row_after_reupload is not None
        assert row_after_reupload.method == "manual"
        assert row_after_reupload.confidence == Decimal("1.00")
