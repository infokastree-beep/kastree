"""Load Copilot tool inputs from the DB under org RLS.

Every query runs on a session that already has ``app.current_org_id`` set
(via ``get_auth_context`` / ``aset_rls_org_id``). Ownership is still checked
explicitly with the same join pattern used by variance / risk / performance
endpoints — defence in depth, never cross-company.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.company import Company
from app.models.financial_statement import FinancialStatement
from app.models.risk_flag import RiskFlag
from app.models.statement_line_item import StatementLineItem
from app.models.trial_balance import TrialBalance
from app.models.variance_analysis import VarianceAnalysis
from app.schemas.commentary import CommentaryRecord
from app.schemas.risk import AffectedAccount, RiskFlagRecord
from app.schemas.variance import VarianceItemRecord
from app.services.performance import (
    METRIC_CODES,
    PeriodMetrics,
    build_period_metrics,
    select_history_periods,
)
from app.services.prior_period import find_prior_trial_balance


@dataclass(frozen=True, slots=True)
class CopilotSessionContext:
    """Owned TB session context for one Copilot ask."""

    tb: TrialBalance
    company: Company
    org_id: uuid.UUID
    prior_period_end: date | None


async def load_owned_copilot_context(
    session: AsyncSession,
    *,
    tb_id: uuid.UUID,
    org_id: uuid.UUID,
) -> CopilotSessionContext:
    """Resolve the TB under org ownership; raise 404 if not visible."""
    result = await session.execute(
        select(TrialBalance, Company)
        .join(Company, Company.id == TrialBalance.company_id)
        .join(Client, Client.id == Company.client_id)
        .where(
            TrialBalance.id == tb_id,
            TrialBalance.is_deleted.is_(False),
            Client.org_id == org_id,
            Client.is_deleted.is_(False),
            Company.is_deleted.is_(False),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Trial balance not found")
    tb, company = row

    prior = await find_prior_trial_balance(
        session,
        company_id=tb.company_id,
        before_period_end=tb.period_end,
    )
    return CopilotSessionContext(
        tb=tb,
        company=company,
        org_id=org_id,
        prior_period_end=prior.period_end if prior is not None else None,
    )


async def load_performance_periods(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    as_of: date,
    current_tb_id: uuid.UUID,
) -> list[PeriodMetrics]:
    """Multi-period KPI/expense metrics from generated statements (same company)."""
    history_rows = await session.execute(
        select(
            TrialBalance.id,
            TrialBalance.period_end,
            StatementLineItem.line_item_code,
            StatementLineItem.amount,
        )
        .join(FinancialStatement, FinancialStatement.tb_id == TrialBalance.id)
        .join(
            StatementLineItem,
            StatementLineItem.statement_id == FinancialStatement.id,
        )
        .where(
            TrialBalance.company_id == company_id,
            TrialBalance.is_deleted.is_(False),
            TrialBalance.period_end <= as_of,
            StatementLineItem.line_item_code.in_(METRIC_CODES),
        )
        .order_by(TrialBalance.period_end.asc(), TrialBalance.id.asc())
    )

    by_tb: dict[uuid.UUID, dict[str, Any]] = {}
    for row_tb_id, period_end, code, amount in history_rows.all():
        bucket = by_tb.setdefault(
            row_tb_id,
            {"period_end": period_end, "amounts": {}},
        )
        bucket["amounts"].setdefault(code, Decimal(amount))

    built = [
        build_period_metrics(
            tb_id=row_tb_id,
            period_end=payload["period_end"],
            line_amounts=payload["amounts"],
        )
        for row_tb_id, payload in by_tb.items()
    ]
    periods = select_history_periods(built, as_of=as_of)
    if periods and all(p.tb_id != current_tb_id for p in periods):
        current = next((p for p in built if p.tb_id == current_tb_id), None)
        if current is not None:
            periods = [*periods, current]
    return periods


async def load_variance_items(
    session: AsyncSession,
    *,
    tb_id: uuid.UUID,
) -> list[VarianceItemRecord]:
    """Latest variance analysis items for this TB (or empty)."""
    result = await session.execute(
        select(VarianceAnalysis)
        .where(VarianceAnalysis.tb_id == tb_id)
        .order_by(VarianceAnalysis.created_at.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None or not analysis.items:
        return []
    raw_items = analysis.items.get("items", analysis.items)
    if not isinstance(raw_items, list):
        return []
    rows: list[VarianceItemRecord] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        try:
            rows.append(VarianceItemRecord.model_validate(raw))
        except Exception:
            continue
    return rows


async def load_commentaries(
    session: AsyncSession,
    *,
    tb_id: uuid.UUID,
) -> dict[str, CommentaryRecord]:
    """Persisted variance commentary map for this TB (or empty)."""
    result = await session.execute(
        select(VarianceAnalysis)
        .where(VarianceAnalysis.tb_id == tb_id)
        .order_by(VarianceAnalysis.created_at.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None or not analysis.commentary:
        return {}
    raw = analysis.commentary
    if isinstance(raw, dict) and "commentaries" in raw:
        raw = raw["commentaries"]
    if not isinstance(raw, dict):
        return {}
    out: dict[str, CommentaryRecord] = {}
    for code, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        try:
            out[str(code)] = CommentaryRecord.model_validate(payload)
        except Exception:
            continue
    return out


async def load_risk_flags(
    session: AsyncSession,
    *,
    tb_id: uuid.UUID,
) -> list[RiskFlagRecord]:
    """Risk flags stored for this TB."""
    result = await session.execute(
        select(RiskFlag)
        .where(RiskFlag.tb_id == tb_id)
        .order_by(RiskFlag.created_at.asc())
    )
    rows: list[RiskFlagRecord] = []
    for flag in result.scalars().all():
        affected: list[AffectedAccount] | None = None
        if flag.affected_accounts:
            raw_accounts = flag.affected_accounts
            if isinstance(raw_accounts, dict) and "accounts" in raw_accounts:
                raw_accounts = raw_accounts["accounts"]
            if isinstance(raw_accounts, list):
                parsed: list[AffectedAccount] = []
                for acct in raw_accounts:
                    if not isinstance(acct, dict):
                        continue
                    try:
                        parsed.append(AffectedAccount.model_validate(acct))
                    except Exception:
                        continue
                affected = parsed or None
        rows.append(
            RiskFlagRecord(
                rule_name=flag.rule_name,
                severity=flag.severity,  # type: ignore[arg-type]
                description=flag.description,
                affected_accounts=affected,
                recommended_action=flag.recommended_action,
            )
        )
    return rows
