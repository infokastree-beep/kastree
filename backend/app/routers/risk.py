"""Risk flag routes — POST/GET /trial-balances/{id}/risk (§10.2).

Rule 2 (unusual variance) needs historical_variance_pcts. There is no
monthly-history table in §9.1, so this router always passes an empty mapping.
Section 4.3 correctly skips Rule 2 when history length < 3 — that is intentional
MVP behaviour, not fabricated history.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.account_mapping import AccountMapping
from app.models.risk_flag import RiskFlag
from app.models.trial_balance import TrialBalance
from app.models.variance_analysis import VarianceAnalysis
from app.routers.trial_balances import _get_owned_tb
from app.schemas.risk import AffectedAccount, RiskFlagResponse, RiskFlagsResponse
from app.schemas.variance import VarianceAnalysisResult
from app.services.risk import evaluate_risks
from app.services.tb_pipeline import parsed_rows_from_tb

router = APIRouter(prefix="/trial-balances", tags=["risk"])

# Explicit empty history — do not invent monthly variance percentages for MVP.
_MVP_HISTORICAL_VARIANCE_PCTS: dict[str, list[Decimal]] = {}


class _RiskAccountAdapter:
    __slots__ = ("account_code", "account_name", "net_balance", "canonical_line")

    def __init__(
        self,
        *,
        account_code: str,
        account_name: str,
        net_balance: Decimal,
        canonical_line: str,
    ) -> None:
        self.account_code = account_code
        self.account_name = account_name
        self.net_balance = net_balance
        self.canonical_line = canonical_line


async def _load_risk_accounts(
    session: AsyncSession,
    tb: TrialBalance,
) -> list[_RiskAccountAdapter]:
    """Mapped TB accounts for Rule 1 (negative cash), from parsed_data + mappings."""
    if not tb.parsed_data:
        raise HTTPException(
            status_code=400,
            detail="Trial balance must be parsed before risk analysis",
        )

    rows = parsed_rows_from_tb(tb)
    mappings = list(
        (
            await session.execute(
                select(AccountMapping).where(
                    AccountMapping.company_id == tb.company_id,
                    AccountMapping.is_confirmed.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    by_key = {
        (mapping.source_code or "", mapping.source_name): mapping for mapping in mappings
    }
    accounts: list[_RiskAccountAdapter] = []
    for row in rows:
        mapping = by_key.get((row.account_code, row.account_name))
        if mapping is None or mapping.canonical_line == "unmapped":
            continue
        accounts.append(
            _RiskAccountAdapter(
                account_code=row.account_code,
                account_name=row.account_name,
                net_balance=row.net_balance,
                canonical_line=mapping.canonical_line,
            )
        )
    return accounts


async def _load_stored_variance(
    session: AsyncSession,
    tb_id: uuid.UUID,
) -> VarianceAnalysisResult | None:
    result = await session.execute(
        select(VarianceAnalysis)
        .where(VarianceAnalysis.tb_id == tb_id)
        .order_by(VarianceAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return VarianceAnalysisResult.model_validate(row.items)


def _flag_to_response(flag: RiskFlag) -> RiskFlagResponse:
    affected: list[AffectedAccount] | None = None
    if flag.affected_accounts is not None:
        raw = flag.affected_accounts
        if isinstance(raw, dict) and "affected_accounts" in raw:
            raw = raw["affected_accounts"]
        if isinstance(raw, list):
            affected = [AffectedAccount.model_validate(item) for item in raw]
    return RiskFlagResponse(
        id=flag.id,
        rule_name=flag.rule_name,
        severity=flag.severity,  # type: ignore[arg-type]
        description=flag.description,
        affected_accounts=affected,
        recommended_action=flag.recommended_action,
    )


@router.post("/{tb_id}/risk", response_model=RiskFlagsResponse)
async def generate_risk_flags(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiskFlagsResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    accounts = await _load_risk_accounts(session, tb)
    variance_result = await _load_stored_variance(session, tb.id)

    # Empty history on purpose — Rule 2 skips when len(history) < 3 (§4.3).
    records = evaluate_risks(
        accounts,
        variance_result=variance_result,
        historical_variance_pcts=_MVP_HISTORICAL_VARIANCE_PCTS,
    )

    existing = await session.execute(select(RiskFlag).where(RiskFlag.tb_id == tb.id))
    for row in existing.scalars().all():
        await session.delete(row)
    await session.flush()

    persisted: list[RiskFlag] = []
    for record in records:
        payload = record.to_jsonb()
        flag = RiskFlag(
            tb_id=tb.id,
            rule_name=record.rule_name,
            severity=record.severity,
            description=record.description,
            affected_accounts=payload.get("affected_accounts"),
            recommended_action=record.recommended_action,
        )
        session.add(flag)
        persisted.append(flag)
    await session.flush()
    for flag in persisted:
        await session.refresh(flag)

    return RiskFlagsResponse(
        tb_id=tb.id,
        flags=[_flag_to_response(flag) for flag in persisted],
        unusual_variance_history_months=0,
    )


@router.get("/{tb_id}/risk", response_model=RiskFlagsResponse)
async def get_risk_flags(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RiskFlagsResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    result = await session.execute(
        select(RiskFlag)
        .where(RiskFlag.tb_id == tb.id)
        .order_by(RiskFlag.created_at.asc())
    )
    flags = list(result.scalars().all())
    return RiskFlagsResponse(
        tb_id=tb.id,
        flags=[_flag_to_response(flag) for flag in flags],
        unusual_variance_history_months=0,
    )
