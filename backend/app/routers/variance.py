"""Variance analysis routes — POST/GET /trial-balances/{id}/variance (§10.2 / §10.3)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.client import Client
from app.models.company import Company
from app.models.financial_statement import FinancialStatement
from app.models.statement_line_item import StatementLineItem
from app.models.trial_balance import TrialBalance
from app.models.variance_analysis import VarianceAnalysis
from app.routers.trial_balances import _get_owned_tb
from app.schemas.commentary import CommentaryRecord, VarianceCommentaryResult
from app.schemas.variance import (
    MISSING_PRIOR_PERIOD_MESSAGE,
    PRIOR_STATEMENTS_MISSING_MESSAGE,
    VarianceAnalysisResult,
    VarianceGenerateRequest,
    VarianceItemResponse,
    VarianceResponse,
)
from app.services.prior_period import find_prior_trial_balance
from app.services.variance import compute_variance

router = APIRouter(prefix="/trial-balances", tags=["variance"])


class _LineAdapter(BaseModel):
    """Adapts StatementLineItem ORM rows to variance.StatementLineLike."""

    line_item_code: str
    line_item_name: str
    amount: Decimal
    is_subtotal: bool


async def _resolve_prior_tb(
    session: AsyncSession,
    *,
    current: TrialBalance,
    prior_tb_id: uuid.UUID | None,
) -> TrialBalance | None:
    """Explicit prior_tb_id, or most recent same-company TB with period_end < current (§6.2)."""
    if prior_tb_id is not None:
        if prior_tb_id == current.id:
            raise HTTPException(status_code=400, detail="prior_tb_id must differ from current TB")
        result = await session.execute(
            select(TrialBalance).where(
                TrialBalance.id == prior_tb_id,
                TrialBalance.company_id == current.company_id,
            )
        )
        prior = result.scalar_one_or_none()
        if prior is None:
            raise HTTPException(status_code=404, detail="Prior trial balance not found")
        return prior

    return await find_prior_trial_balance(
        session,
        company_id=current.company_id,
        before_period_end=current.period_end,
    )


async def _tb_has_sopl_sofp_statements(
    session: AsyncSession,
    tb_id: uuid.UUID,
) -> bool:
    """True when both SOPL and SOFP financial_statements rows exist for this TB."""
    result = await session.execute(
        select(FinancialStatement.statement_type).where(
            FinancialStatement.tb_id == tb_id,
            FinancialStatement.statement_type.in_(("SOPL", "SOFP")),
        )
    )
    types = {row[0] for row in result.all()}
    return "SOPL" in types and "SOFP" in types


async def _load_sopl_sofp_lines(
    session: AsyncSession,
    tb_id: uuid.UUID,
) -> list[_LineAdapter] | None:
    """Read already-built statement_line_items (statements.py output), not remapped accounts.

    Returns None when SOPL/SOFP have not been generated yet — callers must not invent lines.
    """
    if not await _tb_has_sopl_sofp_statements(session, tb_id):
        return None
    statements = await session.execute(
        select(FinancialStatement).where(
            FinancialStatement.tb_id == tb_id,
            FinancialStatement.statement_type.in_(("SOPL", "SOFP")),
        )
    )
    statement_ids = [row.id for row in statements.scalars().all()]
    lines_result = await session.execute(
        select(StatementLineItem)
        .where(StatementLineItem.statement_id.in_(statement_ids))
        .order_by(StatementLineItem.display_order)
    )
    return [
        _LineAdapter(
            line_item_code=line.line_item_code,
            line_item_name=line.line_item_name,
            amount=line.amount,
            is_subtotal=line.is_subtotal,
        )
        for line in lines_result.scalars().all()
    ]


def _unavailable_response(
    tb_id: uuid.UUID,
    *,
    message: str = MISSING_PRIOR_PERIOD_MESSAGE,
    prior_tb_id: uuid.UUID | None = None,
) -> VarianceResponse:
    return VarianceResponse(
        tb_id=tb_id,
        prior_tb_id=prior_tb_id,
        variance_available=False,
        message=message,
        items=[],
    )


def _items_with_commentary(
    analysis: VarianceAnalysisResult,
    commentary_blob: dict | None,
) -> list[VarianceItemResponse]:
    commentaries: dict[str, CommentaryRecord] = {}
    if commentary_blob:
        try:
            parsed = VarianceCommentaryResult.model_validate(commentary_blob)
            commentaries = parsed.commentaries
        except ValidationError:
            commentaries = {}

    return [
        VarianceItemResponse(
            line_item_code=item.line_item_code,
            line_item_name=item.line_item_name,
            current_amount=item.current_amount,
            prior_amount=item.prior_amount,
            variance_amount=item.variance_amount,
            variance_pct=item.variance_pct,
            direction=item.direction,
            is_material=item.is_material,
            commentary=commentaries.get(item.line_item_code),
        )
        for item in analysis.items
    ]


def _analysis_response(
    *,
    tb_id: uuid.UUID,
    prior_tb_id: uuid.UUID,
    company: Company,
    row: VarianceAnalysis,
) -> VarianceResponse:
    analysis = VarianceAnalysisResult.model_validate(row.items)
    return VarianceResponse(
        tb_id=tb_id,
        prior_tb_id=prior_tb_id,
        variance_available=True,
        message=None,
        materiality_threshold_pct=float(company.materiality_threshold_pct),
        materiality_threshold_abs=f"{Decimal(company.materiality_threshold_abs):.2f}",
        items=_items_with_commentary(analysis, row.commentary),
    )


@router.post("/{tb_id}/variance", response_model=VarianceResponse)
async def generate_variance(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    body: VarianceGenerateRequest | None = None,
) -> VarianceResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    company = await session.get(Company, tb.company_id)
    if company is None or company.is_deleted:
        raise HTTPException(status_code=404, detail="Company not found")
    client = await session.get(Client, company.client_id)
    if client is None or client.org_id != auth.org_id or client.is_deleted:
        raise HTTPException(status_code=404, detail="Client not found")

    request = body or VarianceGenerateRequest()
    prior = await _resolve_prior_tb(session, current=tb, prior_tb_id=request.prior_tb_id)
    if prior is None:
        return _unavailable_response(tb.id)

    current_lines = await _load_sopl_sofp_lines(session, tb.id)
    if current_lines is None:
        raise HTTPException(
            status_code=400,
            detail="Statements must be generated before variance analysis",
        )
    prior_lines = await _load_sopl_sofp_lines(session, prior.id)
    if prior_lines is None:
        # Prior TB exists but statements never built — same unavailable shape as no-prior (§7).
        return _unavailable_response(
            tb.id,
            message=PRIOR_STATEMENTS_MISSING_MESSAGE,
            prior_tb_id=prior.id,
        )

    result = compute_variance(
        current_lines,
        prior_lines,
        materiality_threshold_pct=Decimal(company.materiality_threshold_pct),
        materiality_threshold_abs=Decimal(company.materiality_threshold_abs),
    )
    # Persist the canonical JSONB shape — round-trips via VarianceAnalysisResult.
    items_jsonb = result.to_jsonb()

    existing = await session.execute(
        select(VarianceAnalysis).where(VarianceAnalysis.tb_id == tb.id)
    )
    for row in existing.scalars().all():
        await session.delete(row)
    await session.flush()

    row = VarianceAnalysis(
        tb_id=tb.id,
        prior_tb_id=prior.id,
        items=items_jsonb,
        commentary=None,
        status="complete",
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)

    return _analysis_response(
        tb_id=tb.id,
        prior_tb_id=prior.id,
        company=company,
        row=row,
    )


@router.get("/{tb_id}/variance", response_model=VarianceResponse)
async def get_variance(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> VarianceResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    company = await session.get(Company, tb.company_id)
    if company is None or company.is_deleted:
        raise HTTPException(status_code=404, detail="Company not found")
    client = await session.get(Client, company.client_id)
    if client is None or client.org_id != auth.org_id or client.is_deleted:
        raise HTTPException(status_code=404, detail="Client not found")

    result = await session.execute(
        select(VarianceAnalysis)
        .where(VarianceAnalysis.tb_id == tb.id)
        .order_by(VarianceAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        # No stored analysis — check whether a prior period exists for a clear banner.
        prior = await _resolve_prior_tb(session, current=tb, prior_tb_id=None)
        if prior is None:
            return _unavailable_response(tb.id)
        raise HTTPException(status_code=404, detail="Variance analysis not generated yet")

    if row.prior_tb_id is None:
        return _unavailable_response(tb.id)

    return _analysis_response(
        tb_id=tb.id,
        prior_tb_id=row.prior_tb_id,
        company=company,
        row=row,
    )
