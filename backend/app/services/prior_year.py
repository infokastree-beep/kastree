"""Manual prior-year balances and the V-GATE-001 hard gate.

Amounts are Decimal strings. The gate result comes from the engine.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.prior_year_line import PriorYearLine
from findraft.engine.lines import CONSUMED
from findraft.engine.money import D, money
from findraft.engine.reconciliation import check_prior_year_gate
from findraft.models.year_end import YearEnd


class PriorYearRejected(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def canonical_amount(raw: str) -> Decimal:
    """Accept an exact cent amount written as a string."""
    try:
        parsed = D(raw.strip())
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise PriorYearRejected("Amount must be a decimal string") from exc
    cents = money(parsed)
    if cents != parsed:
        raise PriorYearRejected("Amount is not exact to the cent")
    return cents


async def confirm_prior_year(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    lines: list[tuple[str, str]],
) -> list[PriorYearLine]:
    if year_end.prior_year_validated:
        raise PriorYearRejected("Prior year is already validated")
    if year_end.first_financial_period:
        raise PriorYearRejected("This year end is a first financial period")
    if not lines:
        raise PriorYearRejected("Prior-year entry needs at least one canonical line")
    seen: set[str] = set()
    prepared: list[tuple[str, Decimal]] = []
    for name, raw_amount in lines:
        if name not in CONSUMED:
            raise PriorYearRejected(f"Unknown canonical line: {name}")
        if name in seen:
            raise PriorYearRejected(f"Duplicate canonical line: {name}")
        seen.add(name)
        prepared.append((name, canonical_amount(raw_amount)))

    await aset_rls_org_id(session, org_id)
    existing = (
        await session.scalars(
            select(PriorYearLine).where(PriorYearLine.year_end_id == year_end.id)
        )
    ).all()
    for row in existing:
        await session.delete(row)
    await session.flush()
    stored: list[PriorYearLine] = []
    for name, amount in prepared:
        row = PriorYearLine(
            org_id=year_end.org_id,
            company_id=year_end.company_id,
            year_end_id=year_end.id,
            canonical_line=name,
            amount=amount,
        )
        session.add(row)
        stored.append(row)
    year_end.prior_year_validated = True
    await session.flush()
    return stored


async def mark_first_financial_period(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> YearEnd:
    if year_end.prior_year_validated:
        raise PriorYearRejected("Prior year is already validated")
    await aset_rls_org_id(session, org_id)
    existing = (
        await session.scalars(
            select(PriorYearLine).where(PriorYearLine.year_end_id == year_end.id)
        )
    ).all()
    for row in existing:
        await session.delete(row)
    year_end.first_financial_period = True
    year_end.prior_year_validated = True
    await session.flush()
    return year_end


def reconciliation_gate(year_end: YearEnd) -> dict[str, object]:
    """Stop when the engine gate returns a result. Do not run later checks."""
    result = check_prior_year_gate(year_end.prior_year_validated)
    if result is None:
        return {
            "open": True,
            "code": None,
            "severity": None,
            "passed": None,
            "message": None,
        }
    return {
        "open": False,
        "code": result.code,
        "severity": result.severity,
        "passed": result.passed,
        "message": result.message,
    }
