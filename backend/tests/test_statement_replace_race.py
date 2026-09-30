"""Concurrent statement replace must leave one SOPL, SOFP, and SOCIE."""

from __future__ import annotations

import threading
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.financial_statement import FinancialStatement
from app.models.trial_balance import TrialBalance
from app.routers.trial_balances import _persist_statements_for_tb


def test_concurrent_statement_replace_keeps_one_row_per_type(provisioned_org: dict) -> None:
    """Eight overlapping replaces — the path confirm-mapping auto-generate uses.

    Generate Statements also calls this function. The request holds a row lock
    on the trial balance, which hides the race. Confirm commits that lock
    before persisting, so two workers can enter together.
    """
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    tb_id = uuid.uuid4()
    rows = [
        ("1000", "Cash", "5000.00", "0.00", "5000.00", "cash"),
        ("1100", "Trade Debtors", "2000.00", "0.00", "2000.00", "trade_receivables"),
        ("6100", "Rent", "2000.00", "0.00", "2000.00", "operating_expenses"),
        ("2100", "Trade Creditors", "0.00", "1000.00", "-1000.00", "trade_payables"),
        ("3000", "Share Capital", "0.00", "3000.00", "-3000.00", "share_capital"),
        ("3100", "Retained Earnings", "0.00", "1000.00", "-1000.00", "retained_earnings"),
        ("4000", "Sales", "0.00", "4000.00", "-4000.00", "revenue"),
    ]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            TrialBalance(
                id=tb_id,
                company_id=company_id,
                period_end=date(2026, 2, 28),
                file_url=f"file:///tmp/{tb_id}.xlsx",
                file_type="xlsx",
                status="complete",
                currency="EUR",
                parsed_data={
                    "rows": [
                        {
                            "account_code": code,
                            "account_name": name,
                            "debit": debit,
                            "credit": credit,
                            "net_balance": net,
                            "currency": "EUR",
                            "row_index": index,
                        }
                        for index, (code, name, debit, credit, net, _line) in enumerate(rows)
                    ]
                },
            )
        )
        for code, name, _debit, _credit, _net, line in rows:
            session.add(
                AccountMapping(
                    company_id=company_id,
                    source_code=code,
                    source_name=name,
                    canonical_line=line,
                    confidence=Decimal("1.00"),
                    method="manual",
                    is_confirmed=True,
                    is_ignored=False,
                )
            )
        session.commit()

    barrier = threading.Barrier(8)
    errors: list[str] = []

    def replace_once() -> None:
        barrier.wait(timeout=30)
        try:
            with SyncSessionLocal() as session:
                set_rls_org_id(session, org_id)
                tb = session.get(TrialBalance, tb_id)
                assert tb is not None
                _persist_statements_for_tb(session, tb)
                session.commit()
        except Exception as exc:  # noqa: BLE001 — the assertion reports the failure
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=replace_once) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert errors == []
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        counts = dict(
            session.execute(
                select(FinancialStatement.statement_type, func.count())
                .where(FinancialStatement.tb_id == tb_id)
                .group_by(FinancialStatement.statement_type)
            ).all()
        )
    assert counts == {"SOPL": 1, "SOFP": 1, "SOCIE": 1}
