"""Week 6 reconciliation: TB, balance sheet, retained earnings, consumed lines.

The engine owns the checks and the statement build. This module loads a
ready trial balance and its confirmed mappings, then stops when the
prior-year gate is closed. Unconfirmed suggestions never reach aggregate().
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.confirmed_mapping import ConfirmedMapping
from app.models.prior_year_line import PriorYearLine
from app.models.tb_version import TrialBalanceLine, TrialBalanceVersion
from findraft.engine.lines import CONSUMED, SIGN_HOMES
from findraft.engine.mapping import aggregate
from findraft.engine.money import money
from findraft.engine.reconciliation import (
    CheckResult,
    check_bs_balances,
    check_prior_year_gate,
    check_re_rollforward,
    check_tb_integrity,
    check_unmapped,
)
from findraft.engine.schemas import TBLine
from findraft.engine.statements import build_sofp
from findraft.models.year_end import YearEnd


class ReconciliationRejected(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def statutory_lines() -> frozenset[str]:
    """Presented lines plus the sign-home sources aggregate() reclassifies."""
    return CONSUMED | frozenset(SIGN_HOMES)


@dataclass(frozen=True)
class ReconciliationCheck:
    code: str
    severity: str
    passed: bool
    message: str


@dataclass(frozen=True)
class ReconciliationReport:
    blocked: bool
    build_error: str | None
    checks: tuple[ReconciliationCheck, ...]
    net_assets: Decimal | None
    profit: Decimal | None


def _recorded(result: CheckResult) -> ReconciliationCheck:
    return ReconciliationCheck(
        code=result.code,
        severity=result.severity,
        passed=result.passed,
        message=result.message,
    )


def build_reconciliation(
    *,
    prior_year_validated: bool,
    tb_lines: list[TBLine],
    mappings: dict[str, str],
    prior_retained_earnings: Decimal,
) -> ReconciliationReport:
    """Run V-TB-001, V-BS-001 and V-RE-001. The gate stops the rest.

    ``prior_retained_earnings`` is the stored debit-positive prior balance.
    The roll-forward uses its equity presentation, which is the negation.
    A consumed-lines failure from ``build_sofp`` is a build error, not a check id.
    """
    gate = check_prior_year_gate(prior_year_validated)
    if gate is not None:
        return ReconciliationReport(
            blocked=True,
            build_error=None,
            checks=(_recorded(gate),),
            net_assets=None,
            profit=None,
        )

    checks: list[ReconciliationCheck] = [_recorded(check_tb_integrity(tb_lines))]
    mapped = check_unmapped(tb_lines, mappings)
    checks.append(_recorded(mapped))
    if not mapped.passed:
        return ReconciliationReport(
            blocked=False,
            build_error=None,
            checks=tuple(checks),
            net_assets=None,
            profit=None,
        )

    aggregated = aggregate(tb_lines, mappings)
    try:
        sofp = build_sofp(aggregated, {})
    except ValueError as exc:
        return ReconciliationReport(
            blocked=False,
            build_error=str(exc),
            checks=tuple(checks),
            net_assets=None,
            profit=None,
        )

    checks.append(_recorded(check_bs_balances(sofp)))
    closing = next(
        current
        for label, current, _prior in sofp["rows"]
        if label == "Profit and loss account"
    )
    dividends = money(aggregated.get("DIVIDENDS", Decimal("0")))
    opening = money(-prior_retained_earnings)
    checks.append(
        _recorded(check_re_rollforward(opening, sofp["profit"], dividends, closing))
    )
    return ReconciliationReport(
        blocked=False,
        build_error=None,
        checks=tuple(checks),
        net_assets=sofp["net_assets"],
        profit=sofp["profit"],
    )


async def confirm_mappings(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    version: TrialBalanceVersion,
    lines: list[tuple[str, str]],
) -> list[ConfirmedMapping]:
    """Store one confirmed line per trial-balance code. Refuses a second write."""
    if version.status != "ready":
        raise ReconciliationRejected("Trial balance version is not ready")
    await aset_rls_org_id(session, org_id)
    existing = (
        await session.scalars(
            select(ConfirmedMapping.id).where(
                ConfirmedMapping.tb_version_id == version.id,
                ConfirmedMapping.org_id == org_id,
            )
        )
    ).first()
    if existing is not None:
        raise ReconciliationRejected("Mappings are already confirmed", 409)

    tb_rows = (
        await session.scalars(
            select(TrialBalanceLine)
            .where(
                TrialBalanceLine.tb_version_id == version.id,
                TrialBalanceLine.org_id == org_id,
            )
            .order_by(TrialBalanceLine.line_no)
        )
    ).all()
    expected = {row.nominal_code for row in tb_rows}
    if not expected:
        raise ReconciliationRejected("Trial balance version has no lines")

    seen: set[str] = set()
    prepared: list[tuple[str, str]] = []
    allowed = statutory_lines()
    for code, canonical in lines:
        nominal = code.strip()
        line_name = canonical.strip()
        if not nominal or not line_name:
            raise ReconciliationRejected(
                "Each mapping needs a code and a canonical line"
            )
        if nominal in seen:
            raise ReconciliationRejected(f"Duplicate nominal code: {nominal}")
        if nominal not in expected:
            raise ReconciliationRejected(f"Unknown nominal code: {nominal}")
        if line_name not in allowed:
            raise ReconciliationRejected(f"Unknown canonical line: {line_name}")
        seen.add(nominal)
        prepared.append((nominal, line_name))
    missing = expected - seen
    if missing:
        raise ReconciliationRejected(
            "Every trial-balance line needs a confirmed mapping: "
            + ", ".join(sorted(missing))
        )

    stored: list[ConfirmedMapping] = []
    for nominal, line_name in prepared:
        row = ConfirmedMapping(
            org_id=year_end.org_id,
            company_id=year_end.company_id,
            tb_version_id=version.id,
            nominal_code=nominal,
            canonical_line=line_name,
        )
        session.add(row)
        stored.append(row)
    await session.flush()
    return stored


async def reconcile_version(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    version: TrialBalanceVersion,
) -> ReconciliationReport:
    """Load confirmed mappings only. A pending version is not reconciled."""
    gate = check_prior_year_gate(year_end.prior_year_validated)
    if gate is not None:
        return build_reconciliation(
            prior_year_validated=False,
            tb_lines=[],
            mappings={},
            prior_retained_earnings=Decimal("0"),
        )
    if version.status != "ready":
        raise ReconciliationRejected("Trial balance version is not ready")

    await aset_rls_org_id(session, org_id)
    tb_rows = (
        await session.scalars(
            select(TrialBalanceLine)
            .where(
                TrialBalanceLine.tb_version_id == version.id,
                TrialBalanceLine.org_id == org_id,
            )
            .order_by(TrialBalanceLine.line_no)
        )
    ).all()
    mapping_rows = (
        await session.scalars(
            select(ConfirmedMapping).where(
                ConfirmedMapping.tb_version_id == version.id,
                ConfirmedMapping.org_id == org_id,
            )
        )
    ).all()
    prior_rows = (
        await session.scalars(
            select(PriorYearLine).where(
                PriorYearLine.year_end_id == year_end.id,
                PriorYearLine.org_id == org_id,
            )
        )
    ).all()
    prior_re = Decimal("0")
    for row in prior_rows:
        if row.canonical_line == "RETAINED_EARNINGS":
            prior_re = row.amount
    return build_reconciliation(
        prior_year_validated=True,
        tb_lines=[
            TBLine(
                nominal_code=row.nominal_code,
                account_name=row.account_name,
                debit=row.debit,
                credit=row.credit,
            )
            for row in tb_rows
        ],
        mappings={row.nominal_code: row.canonical_line for row in mapping_rows},
        prior_retained_earnings=prior_re,
    )
