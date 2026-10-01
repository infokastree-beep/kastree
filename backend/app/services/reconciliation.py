"""Reconciliation v1 and v2.

The engine owns the checks and the statement build. This module loads a
ready trial balance, its confirmed mappings, the prior-year canonical
balances, and the latest ready fixed-asset register. It stops when the
prior-year gate is closed. Unconfirmed suggestions never reach aggregate().

Bank reconciliation is the row 13 product cut. This module does not call
check_bank_reconciliation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.confirmed_mapping import ConfirmedMapping
from app.models.fa_version import FixedAssetLine, FixedAssetVersion
from app.models.prior_year_line import PriorYearLine
from app.models.tb_version import TrialBalanceLine, TrialBalanceVersion
from findraft.engine.lines import CONSUMED, SIGN_HOMES
from findraft.engine.mapping import aggregate
from findraft.engine.money import money
from findraft.engine.notes import build_fa_grid
from findraft.engine.pack import pack_dir
from findraft.engine.reconciliation import (
    CheckResult,
    check_bs_balances,
    check_comparatives,
    check_fa_rollforward,
    check_prior_year_gate,
    check_re_rollforward,
    check_tb_integrity,
    check_unmapped,
    review_rules,
)
from findraft.engine.schemas import TBLine
from findraft.engine.statements import (
    IS_KEYS,
    SOFP_KEYS,
    build_income_statement,
    build_sofp,
    prior_from_mapped,
)
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


def _default_rules_path() -> Path:
    return pack_dir() / "review-rules.json"


def _row_current(sofp: dict[str, object], label: str) -> Decimal:
    rows = sofp["rows"]
    if not isinstance(rows, list):
        raise ValueError("statement rows are missing")
    for item in rows:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        row_label, current = item[0], item[1]
        if row_label == label and isinstance(current, Decimal):
            return current
    raise ValueError(f"statement row missing: {label}")


def _fa_check(
    sofp: dict[str, object],
    fa_register: dict[str, dict[str, Decimal]] | None,
) -> ReconciliationCheck:
    """Roll the register forward through the engine check.

    With no ready register, a non-zero fixed-asset face fails the same check.
    Passing zeros against zeros would hide a missing register.
    """
    if fa_register:
        grid = build_fa_grid(fa_register)
        total = grid[-2]
        disposed = money(total["disposals"] - total["disposals_dep"])
        return _recorded(
            check_fa_rollforward(
                total["nbv_open"],
                total["additions"],
                total["charge"],
                disposed,
                total["nbv_close"],
            )
        )
    closing = money(
        _row_current(sofp, "Tangible assets") + _row_current(sofp, "Intangible assets")
    )
    zero = Decimal("0")
    return _recorded(check_fa_rollforward(zero, zero, zero, zero, closing))


def _presented_comparatives(
    sofp: dict[str, object],
    income: dict[str, object],
    validated: dict[str, Decimal],
) -> dict[str, Decimal]:
    """Read the comparative column back into the prior_from_mapped key space."""
    presented: dict[str, Decimal] = {}
    sofp_rows = sofp["rows"]
    if isinstance(sofp_rows, list):
        for item in sofp_rows:
            if not isinstance(item, tuple) or len(item) < 3:
                continue
            label, comparative = item[0], item[2]
            key = SOFP_KEYS.get(str(label))
            if key is not None and isinstance(comparative, Decimal):
                presented[key] = comparative
    face: dict[str, Decimal] = {}
    income_rows = income["rows"]
    if isinstance(income_rows, list):
        for item in income_rows:
            if not isinstance(item, tuple) or len(item) < 3:
                continue
            label, comparative = item[0], item[2]
            if isinstance(comparative, Decimal):
                face[str(label)] = comparative
    for label, (key, sign) in IS_KEYS.items():
        if label.startswith("Administrative"):
            continue
        comparative = face.get(label)
        if comparative is None:
            continue
        presented[key] = money(Decimal(sign) * comparative)
    admin = face.get("Administrative expenses (including depreciation)")
    admin_prior = validated.get("ADMIN_EXPENSES")
    depreciation = validated.get("DEPRECIATION")
    if admin is not None and admin_prior is not None and depreciation is not None:
        expected = money(-(admin_prior + depreciation))
        if admin == expected:
            presented["ADMIN_EXPENSES"] = admin_prior
            presented["DEPRECIATION"] = depreciation
    return presented


def build_reconciliation(
    *,
    prior_year_validated: bool,
    tb_lines: list[TBLine],
    mappings: dict[str, str],
    prior_retained_earnings: Decimal,
    prior_canonical: dict[str, Decimal] | None = None,
    fa_register: dict[str, dict[str, Decimal]] | None = None,
    pack_rules_path: Path | None = None,
) -> ReconciliationReport:
    """Run the engine checks. The gate stops the rest.

    ``prior_retained_earnings`` is the stored debit-positive prior balance.
    The roll-forward uses its equity presentation, which is the negation.
    ``prior_canonical`` is every stored prior-year line, same sign convention.
    Comparatives are that map rendered by ``prior_from_mapped``.
    A consumed-lines failure from ``build_sofp`` is a build error, not a check id.
    A pack rule that cannot be evaluated stays CRITICAL.
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
    canonical = prior_canonical or {}
    try:
        validated = prior_from_mapped(canonical)
        sofp = build_sofp(aggregated, validated)
        income = build_income_statement(aggregated, validated)
    except ValueError as exc:
        return ReconciliationReport(
            blocked=False,
            build_error=str(exc),
            checks=tuple(checks),
            net_assets=None,
            profit=None,
        )

    checks.append(_recorded(check_bs_balances(sofp)))
    checks.append(_fa_check(sofp, fa_register))
    closing = _row_current(sofp, "Profit and loss account")
    dividends = money(aggregated.get("DIVIDENDS", Decimal("0")))
    opening = money(-prior_retained_earnings)
    checks.append(
        _recorded(check_re_rollforward(opening, sofp["profit"], dividends, closing))
    )
    for result in check_comparatives(
        _presented_comparatives(sofp, income, validated), validated
    ):
        checks.append(_recorded(result))

    rules_path = (
        pack_rules_path if pack_rules_path is not None else _default_rules_path()
    )
    try:
        hits = review_rules(
            aggregated,
            {},
            sofp["profit"],
            pack_path=rules_path,
            opening_re=opening,
        )
    except (OSError, ValueError) as exc:
        return ReconciliationReport(
            blocked=False,
            build_error=str(exc),
            checks=tuple(checks),
            net_assets=sofp["net_assets"],
            profit=sofp["profit"],
        )
    for hit in hits:
        checks.append(_recorded(hit))
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
    prior_canonical = {row.canonical_line: row.amount for row in prior_rows}
    prior_re = prior_canonical.get("RETAINED_EARNINGS", Decimal("0"))
    fa_version = (
        await session.scalars(
            select(FixedAssetVersion)
            .where(
                FixedAssetVersion.year_end_id == year_end.id,
                FixedAssetVersion.org_id == org_id,
                FixedAssetVersion.status == "ready",
            )
            .order_by(FixedAssetVersion.version_number.desc())
            .limit(1)
        )
    ).first()
    fa_register: dict[str, dict[str, Decimal]] | None = None
    if fa_version is not None:
        fa_lines = (
            await session.scalars(
                select(FixedAssetLine)
                .where(
                    FixedAssetLine.fa_version_id == fa_version.id,
                    FixedAssetLine.org_id == org_id,
                )
                .order_by(FixedAssetLine.line_no)
            )
        ).all()
        if fa_lines:
            fa_register = {
                line.asset_class: {
                    "opening_cost": line.opening_cost,
                    "additions": line.additions,
                    "disposals": line.disposals,
                    "disposals_dep": line.disposals_dep,
                    "opening_dep": line.opening_dep,
                    "charge": line.charge,
                }
                for line in fa_lines
            }
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
        prior_canonical=prior_canonical,
        fa_register=fa_register,
        pack_rules_path=pack_dir(year_end.pack_id, year_end.pack_version)
        / "review-rules.json",
    )
