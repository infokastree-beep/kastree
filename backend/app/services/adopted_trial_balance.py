"""Adopt a completed Product 1 trial balance into a statutory year end.

The year end stores ``trial_balances.id``. This module does not insert
``findraft_tb_versions``, ``findraft_tb_lines``, or
``findraft_confirmed_mappings``, and it does not ask for a second
confirmation. Confirmed ``account_mappings`` are read live. Continuation
inserts one draft whose trial-balance version id stays null.

Product 1 canonical lines (``revenue``, ``cash``, ``loans``) are not engine
lines. ``engine_line_for_confirmed_mapping`` is the only translation.
A Product 1 line that has no single statutory line is refused. Suggestions
are not consulted.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.account_mapping import AccountMapping
from app.services.audit import append_audit_log
from app.models.company import Company
from app.models.fa_version import FixedAssetLine, FixedAssetVersion
from app.models.prior_year_line import PriorYearLine
from app.models.trial_balance import TrialBalance
from app.services.reconciliation import (
    ConfirmedInputs,
    ReconciliationRejected,
    ReconciliationReport,
    build_reconciliation,
    statutory_lines,
)
from app.services.statutory_sublines import (
    allowed_sublines,
    needs_statutory_subline,
    suggest_subline,
)
from findraft.engine.pack import load_manifest, pack_dir, pin_pack_version
from findraft.engine.reconciliation import check_prior_year_gate
from findraft.engine.schemas import TBLine
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

MAPPING_NOTICE = (
    "Product 1 confirmed mappings changed after this draft was acknowledged. "
    "This draft now uses the current mappings."
)

_DIRECT: dict[str, str] = {
    "revenue": "REVENUE",
    "other_revenue": "OTHER_OPERATING_INCOME",
    "cost_of_sales": "COST_OF_SALES",
    "interest_income": "INTEREST_RECEIVABLE",
    "interest_expense": "INTEREST_PAYABLE",
    "inventory": "STOCKS",
    "trade_receivables": "TRADE_DEBTORS",
    "other_receivables": "OTHER_DEBTORS",
    "prepayments": "PREPAYMENTS",
    "accrued_income": "ACCRUED_INCOME",
    "cash": "CASH",
    "trade_payables": "TRADE_CREDITORS",
    "other_payables": "OTHER_CREDITORS",
    "provisions": "PROVISIONS",
    "accruals": "ACCRUALS",
    "deferred_income": "DEFERRED_INCOME",
    "taxes_payable": "CORP_TAX",
    "social_security_payable": "PAYE_PRSI",
    "share_capital": "SHARE_CAPITAL",
    "share_premium": "SHARE_PREMIUM",
    "retained_earnings": "RETAINED_EARNINGS",
    "dividends": "DIVIDENDS",
    "investments": "FA_INVESTMENTS",
}

@dataclass(frozen=True)
class SourceAccount:
    nominal_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    row_index: int


@dataclass(frozen=True)
class ConfirmedAccount:
    canonical_line: str
    is_confirmed: bool
    is_ignored: bool
    statutory_line: str | None = None


@dataclass(frozen=True)
class CarriedMapping:
    nominal_code: str
    account_name: str
    product1_line: str
    canonical_line: str | None
    suggested_line: str | None = None
    suggestion_confidence: Decimal | None = None


@dataclass(frozen=True)
class AdoptableTrialBalance:
    id: uuid.UUID
    period_end: date
    currency: str | None
    account_count: int


def _subline_gap(product1_line: str, account_name: str) -> str:
    return (
        f"Product 1 line '{product1_line}' on '{account_name.strip()}' "
        "needs a statutory sub-line"
    )


def resolve_engine_line(
    product1_line: str,
    account_name: str,
    statutory_line: str | None = None,
) -> str | None:
    """Posted engine line, or None when a sub-line is still unconfirmed.

    A name-pattern suggestion is never returned here. Direct Product 1 lines
    ignore ``statutory_line``. An unknown line, or a sub-line outside the
    dropdown for that Product 1 line, raises.
    """
    line = product1_line.strip().casefold()
    name = account_name.strip()
    if not line or not name:
        raise ReconciliationRejected(
            "Each confirmed mapping needs a Product 1 line and an account name"
        )
    if line in _DIRECT:
        engine = _DIRECT[line]
        if engine not in statutory_lines():
            raise ReconciliationRejected(
                f"Product 1 line '{line}' on '{name}' has no single statutory line"
            )
        return engine
    if needs_statutory_subline(line):
        chosen = (statutory_line or "").strip()
        if not chosen:
            return None
        if chosen not in allowed_sublines(line) or chosen not in statutory_lines():
            raise ReconciliationRejected(
                f"Statutory sub-line '{chosen}' is not a home for '{line}'"
            )
        return chosen
    raise ReconciliationRejected(
        f"Product 1 line '{line}' on '{name}' has no single statutory line"
    )


def engine_line_for_confirmed_mapping(
    product1_line: str,
    account_name: str,
    statutory_line: str | None = None,
) -> str:
    """One statutory line for a confirmed Product 1 mapping, or a refusal."""
    engine = resolve_engine_line(product1_line, account_name, statutory_line)
    if engine is None:
        raise ReconciliationRejected(_subline_gap(product1_line, account_name))
    return engine


def source_accounts_from_parsed(parsed: object) -> list[SourceAccount]:
    """Read the Product 1 ``parsed_data`` row list. Amounts stay Decimal."""
    if not isinstance(parsed, dict):
        return []
    payload = cast(Mapping[object, object], parsed)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    accounts: list[SourceAccount] = []
    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise ReconciliationRejected("Trial balance row is not an object")
        row = cast(Mapping[object, object], item)
        code = str(row.get("account_code") or "").strip()
        name = str(row.get("account_name") or "").strip()
        if not code or not name:
            raise ReconciliationRejected(
                "Trial balance row is missing a code or name"
            )
        try:
            debit = Decimal(str(row["debit"]))
            credit = Decimal(str(row["credit"]))
        except (InvalidOperation, KeyError, ValueError) as exc:
            raise ReconciliationRejected(
                "Trial balance amount is not a number"
            ) from exc
        if not debit.is_finite() or not credit.is_finite() or debit < 0 or credit < 0:
            raise ReconciliationRejected(
                f"Trial balance amount for {code} is not a positive Decimal"
            )
        raw_index = row.get("row_index")
        position = raw_index if isinstance(raw_index, int) else index
        accounts.append(
            SourceAccount(
                nominal_code=code,
                account_name=name,
                debit=debit,
                credit=credit,
                row_index=position,
            )
        )
    return accounts


def _suggestion_fields(
    product1_line: str, account_name: str, statutory_line: str | None
) -> tuple[str | None, Decimal | None]:
    if not needs_statutory_subline(product1_line):
        return None, None
    chosen = (statutory_line or "").strip()
    if chosen and chosen in allowed_sublines(product1_line):
        return chosen, Decimal("1.00")
    hit = suggest_subline(product1_line, account_name)
    if hit is None:
        return None, None
    confidence = (Decimal(hit.score) / Decimal("100")).quantize(Decimal("0.01"))
    return hit.engine_line, confidence


def carry_confirmed_accounts(
    accounts: Sequence[SourceAccount],
    mappings: Mapping[tuple[str, str], ConfirmedAccount],
    *,
    require_sublines: bool = True,
) -> tuple[list[TBLine], dict[str, str], tuple[CarriedMapping, ...]]:
    """Carry every confirmed, non-ignored account. Refuses a gap or a clash.

    When ``require_sublines`` is false, an unconfirmed sub-line is carried
    with no engine line so the draft can open. Statement generation uses
    the default and refuses that gap.
    """
    lines: list[TBLine] = []
    engine_by_code: dict[str, str] = {}
    carried: list[CarriedMapping] = []
    seen: set[str] = set()
    ordered = sorted(
        accounts, key=lambda item: (item.row_index, item.nominal_code)
    )
    for account in ordered:
        key = (account.nominal_code, account.account_name)
        mapping = mappings.get(key)
        if mapping is not None and mapping.is_ignored:
            continue
        if mapping is None or not mapping.is_confirmed:
            raise ReconciliationRejected(
                f"Account {account.nominal_code} {account.account_name} "
                "is not confirmed"
            )
        if account.nominal_code in seen:
            raise ReconciliationRejected(
                f"Duplicate nominal code: {account.nominal_code}"
            )
        seen.add(account.nominal_code)
        engine = resolve_engine_line(
            mapping.canonical_line,
            account.account_name,
            mapping.statutory_line,
        )
        if engine is None:
            if require_sublines:
                raise ReconciliationRejected(
                    _subline_gap(mapping.canonical_line, account.account_name)
                )
        else:
            engine_by_code[account.nominal_code] = engine
        suggested, confidence = _suggestion_fields(
            mapping.canonical_line,
            account.account_name,
            mapping.statutory_line,
        )
        lines.append(
            TBLine(
                nominal_code=account.nominal_code,
                account_name=account.account_name,
                debit=account.debit,
                credit=account.credit,
            )
        )
        carried.append(
            CarriedMapping(
                nominal_code=account.nominal_code,
                account_name=account.account_name,
                product1_line=mapping.canonical_line.strip().casefold(),
                canonical_line=engine,
                suggested_line=suggested,
                suggestion_confidence=confidence,
            )
        )
    if not carried:
        raise ReconciliationRejected("Trial balance has no confirmed accounts")
    return lines, engine_by_code, tuple(carried)


def _confirmed_index(
    rows: Sequence[AccountMapping],
) -> dict[tuple[str, str], ConfirmedAccount]:
    return {
        ((row.source_code or "").strip(), row.source_name.strip()): ConfirmedAccount(
            canonical_line=row.canonical_line,
            is_confirmed=row.is_confirmed,
            is_ignored=row.is_ignored,
            statutory_line=row.statutory_line,
        )
        for row in rows
    }


async def _mappings_for_company(
    session: AsyncSession, company_id: uuid.UUID
) -> dict[tuple[str, str], ConfirmedAccount]:
    rows = (
        await session.scalars(
            select(AccountMapping).where(AccountMapping.company_id == company_id)
        )
    ).all()
    return _confirmed_index(rows)


async def list_adoptable_trial_balances(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> list[AdoptableTrialBalance]:
    """Completed Product 1 trial balances whose confirmed mappings all carry."""
    await aset_rls_org_id(session, org_id)
    balances = (
        await session.scalars(
            select(TrialBalance)
            .where(
                TrialBalance.company_id == year_end.company_id,
                TrialBalance.period_end == year_end.period_end,
                TrialBalance.is_deleted.is_(False),
                TrialBalance.status == "complete",
            )
            .order_by(TrialBalance.created_at.desc())
        )
    ).all()
    mappings = await _mappings_for_company(session, year_end.company_id)
    adoptable: list[AdoptableTrialBalance] = []
    for tb in balances:
        try:
            _lines, _engine, carried = carry_confirmed_accounts(
                source_accounts_from_parsed(tb.parsed_data),
                mappings,
                require_sublines=False,
            )
        except ReconciliationRejected:
            continue
        adoptable.append(
            AdoptableTrialBalance(
                id=tb.id,
                period_end=tb.period_end,
                currency=tb.currency,
                account_count=len(carried),
            )
        )
    return adoptable


async def _owned_complete_tb(
    session: AsyncSession, *, year_end: YearEnd, trial_balance_id: uuid.UUID
) -> TrialBalance:
    tb = await session.get(TrialBalance, trial_balance_id)
    if tb is None or tb.company_id != year_end.company_id or tb.is_deleted:
        raise ReconciliationRejected("Trial balance not found", 404)
    if tb.status != "complete":
        raise ReconciliationRejected(
            "Trial balance is not a completed, confirmed Product 1 trial balance"
        )
    if tb.period_end != year_end.period_end:
        raise ReconciliationRejected(
            "Trial balance period_end does not match this year end"
        )
    return tb


async def adopt_confirmed_trial_balance(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    trial_balance_id: uuid.UUID,
) -> tuple[CarriedMapping, ...]:
    """Point the year end at the Product 1 trial balance. No statutory copy."""
    await aset_rls_org_id(session, org_id)
    tb = await _owned_complete_tb(
        session, year_end=year_end, trial_balance_id=trial_balance_id
    )
    mappings = await _mappings_for_company(session, year_end.company_id)
    _lines, _engine, carried = carry_confirmed_accounts(
        source_accounts_from_parsed(tb.parsed_data),
        mappings,
        require_sublines=False,
    )
    year_end.adopted_trial_balance_id = tb.id
    await session.flush()
    return carried


async def continue_from_trial_balance(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    trial_balance: TrialBalance,
    pack_id: str,
    pack_version: str,
) -> tuple[YearEnd, tuple[CarriedMapping, ...]]:
    """Find or create the year end for this trial balance, then adopt it.

    Inserts one draft with a null trial-balance version id. Does not insert
    a statutory trial-balance version. Confirmed Product 1 mappings are
    translated by ``adopt_confirmed_trial_balance``.
    """
    await aset_rls_org_id(session, org_id)
    if trial_balance.status != "complete":
        raise ReconciliationRejected(
            "Trial balance is not a completed, confirmed Product 1 trial balance"
        )
    if trial_balance.period_start is None:
        raise ReconciliationRejected("This trial balance has no period start")
    if trial_balance.period_end < trial_balance.period_start:
        raise ReconciliationRejected("period_end is before period_start")
    company = await session.get(Company, trial_balance.company_id)
    if (
        company is None
        or company.is_deleted
        or company.org_id != org_id
    ):
        raise ReconciliationRejected("Trial balance not found", 404)
    try:
        manifest = load_manifest(pack_dir(pack_id, pack_version) / "pack.json")
        pinned = pin_pack_version(
            {},
            manifest,
            period_start=trial_balance.period_start.isoformat(),
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise ReconciliationRejected(str(exc)) from exc
    pinned_id = str(pinned["pack_id"])
    pinned_version = str(pinned["pack_version"])
    year_end = await _year_end_for_period(
        session,
        org_id=company.org_id,
        company_id=company.id,
        period_end=trial_balance.period_end,
    )
    if year_end is None:
        created = YearEnd(
            org_id=company.org_id,
            company_id=company.id,
            period_start=trial_balance.period_start,
            period_end=trial_balance.period_end,
            pack_id=pinned_id,
            pack_version=pinned_version,
        )
        try:
            async with session.begin_nested():
                session.add(created)
                await session.flush()
        except IntegrityError:
            year_end = await _year_end_for_period(
                session,
                org_id=company.org_id,
                company_id=company.id,
                period_end=trial_balance.period_end,
            )
            if year_end is None:
                raise
        else:
            year_end = created
    if year_end.pack_id != pinned_id or year_end.pack_version != pinned_version:
        raise ReconciliationRejected(
            "A year end for this period is already pinned to "
            f"{year_end.pack_id} {year_end.pack_version}",
            409,
        )
    carried = await adopt_confirmed_trial_balance(
        session,
        org_id=org_id,
        year_end=year_end,
        trial_balance_id=trial_balance.id,
    )
    await ensure_adopted_draft(session, org_id=org_id, year_end=year_end)
    return year_end, carried


async def _year_end_for_period(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    period_end: date,
) -> YearEnd | None:
    found: YearEnd | None = await session.scalar(
        select(YearEnd).where(
            YearEnd.org_id == org_id,
            YearEnd.company_id == company_id,
            YearEnd.period_end == period_end,
        )
    )
    return found


async def _year_end_supplements(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> tuple[dict[str, Decimal], dict[str, dict[str, Decimal]] | None]:
    prior_rows = (
        await session.scalars(
            select(PriorYearLine).where(
                PriorYearLine.year_end_id == year_end.id,
                PriorYearLine.org_id == org_id,
            )
        )
    ).all()
    prior_canonical = {row.canonical_line: row.amount for row in prior_rows}
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
    return prior_canonical, fa_register


async def _adopted_bundle(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> tuple[ConfirmedInputs, tuple[CarriedMapping, ...]]:
    await aset_rls_org_id(session, org_id)
    if year_end.adopted_trial_balance_id is None:
        raise ReconciliationRejected("No confirmed trial balance is selected", 404)
    tb = await _owned_complete_tb(
        session,
        year_end=year_end,
        trial_balance_id=year_end.adopted_trial_balance_id,
    )
    mappings = await _mappings_for_company(session, year_end.company_id)
    tb_lines, engine_by_code, carried = carry_confirmed_accounts(
        source_accounts_from_parsed(tb.parsed_data), mappings
    )
    prior_canonical, fa_register = await _year_end_supplements(
        session, org_id=org_id, year_end=year_end
    )
    loaded = ConfirmedInputs(
        tb_lines=tb_lines,
        mappings=engine_by_code,
        prior_canonical=prior_canonical,
        prior_retained_earnings=prior_canonical.get(
            "RETAINED_EARNINGS", Decimal("0")
        ),
        fa_register=fa_register,
        pack_rules_path=pack_dir(year_end.pack_id, year_end.pack_version)
        / "review-rules.json",
    )
    return loaded, carried


async def load_adopted_inputs(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> ConfirmedInputs:
    """Confirmed Product 1 rows and mappings, plus this year end's supplements."""
    loaded, _carried = await _adopted_bundle(
        session, org_id=org_id, year_end=year_end
    )
    return loaded


def mapping_fingerprint(carried: Sequence[CarriedMapping]) -> str:
    """Hash of the carried engine mapping that affects the statutory face."""
    rows: list[dict[str, str]] = [
        {
            "account_name": item.account_name,
            "canonical_line": item.canonical_line or "",
            "nominal_code": item.nominal_code,
            "product1_line": item.product1_line,
        }
        for item in carried
    ]
    rows.sort(key=lambda row: (row["nominal_code"], row["account_name"]))
    encoded = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def current_mapping_fingerprint(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> str:
    """Hash the live mapping, including rows whose sub-line is still open."""
    await aset_rls_org_id(session, org_id)
    if year_end.adopted_trial_balance_id is None:
        raise ReconciliationRejected("No confirmed trial balance is selected", 404)
    tb = await _owned_complete_tb(
        session,
        year_end=year_end,
        trial_balance_id=year_end.adopted_trial_balance_id,
    )
    mappings = await _mappings_for_company(session, year_end.company_id)
    _lines, _engine, carried = carry_confirmed_accounts(
        source_accounts_from_parsed(tb.parsed_data),
        mappings,
        require_sublines=False,
    )
    return mapping_fingerprint(carried)


def freeze_payload(loaded: ConfirmedInputs) -> dict[str, object]:
    """Computation base captured when a draft stops being the live report."""
    lines: list[dict[str, str]] = [
        {
            "nominal_code": line.nominal_code,
            "account_name": line.account_name,
            "debit": str(line.debit),
            "credit": str(line.credit),
        }
        for line in loaded.tb_lines
    ]
    fa_register: dict[str, dict[str, str]] | None
    if loaded.fa_register is None:
        fa_register = None
    else:
        fa_register = {
            asset: {key: str(amount) for key, amount in sorted(fields.items())}
            for asset, fields in sorted(loaded.fa_register.items())
        }
    payload: dict[str, object] = {
        "tb_lines": lines,
        "mappings": dict(sorted(loaded.mappings.items())),
        "prior_canonical": {
            key: str(amount)
            for key, amount in sorted(loaded.prior_canonical.items())
        },
        "prior_retained_earnings": str(loaded.prior_retained_earnings),
        "fa_register": fa_register,
    }
    return payload


def _frozen_unreadable() -> ReconciliationRejected:
    return ReconciliationRejected("Frozen draft inputs are unreadable")


def inputs_from_frozen(
    payload: dict[str, object], year_end: YearEnd
) -> ConfirmedInputs:
    """Restore a frozen computation base. Pack rules stay on disk."""
    raw_lines = payload.get("tb_lines")
    raw_mappings = payload.get("mappings")
    raw_prior = payload.get("prior_canonical")
    if (
        not isinstance(raw_lines, list)
        or not isinstance(raw_mappings, dict)
        or not isinstance(raw_prior, dict)
        or "prior_retained_earnings" not in payload
    ):
        raise _frozen_unreadable()
    tb_lines: list[TBLine] = []
    for item in raw_lines:
        if not isinstance(item, dict):
            raise _frozen_unreadable()
        tb_lines.append(
            TBLine(
                nominal_code=str(item.get("nominal_code", "")),
                account_name=str(item.get("account_name", "")),
                debit=Decimal(str(item.get("debit", "0"))),
                credit=Decimal(str(item.get("credit", "0"))),
            )
        )
    mappings = {str(key): str(value) for key, value in raw_mappings.items()}
    prior_canonical = {
        str(key): Decimal(str(value)) for key, value in raw_prior.items()
    }
    raw_fa = payload.get("fa_register")
    fa_register: dict[str, dict[str, Decimal]] | None
    if raw_fa is None:
        fa_register = None
    elif isinstance(raw_fa, dict):
        fa_register = {}
        for asset, fields in raw_fa.items():
            if not isinstance(fields, dict):
                raise _frozen_unreadable()
            fa_register[str(asset)] = {
                str(key): Decimal(str(amount)) for key, amount in fields.items()
            }
    else:
        raise _frozen_unreadable()
    return ConfirmedInputs(
        tb_lines=tb_lines,
        mappings=mappings,
        prior_canonical=prior_canonical,
        prior_retained_earnings=Decimal(str(payload["prior_retained_earnings"])),
        fa_register=fa_register,
        pack_rules_path=pack_dir(year_end.pack_id, year_end.pack_version)
        / "review-rules.json",
    )


async def inputs_for_adopted_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion | None,
) -> ConfirmedInputs:
    """Live Product 1 inputs, or the snapshot once the draft is frozen."""
    if draft is not None and draft.is_frozen:
        if not isinstance(draft.frozen_inputs, dict):
            raise _frozen_unreadable()
        return inputs_from_frozen(draft.frozen_inputs, year_end)
    return await load_adopted_inputs(session, org_id=org_id, year_end=year_end)


async def _latest_draft(
    session: AsyncSession, *, org_id: uuid.UUID, year_end_id: uuid.UUID
) -> DraftVersion | None:
    await aset_rls_org_id(session, org_id)
    return (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == year_end_id,
            )
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
    ).first()


async def final_adopted_snapshot(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> dict[str, object] | None:
    """Stored FINAL output for the active adopted draft, once it has been finalised."""
    draft = await active_adopted_draft(session, org_id=org_id, year_end=year_end)
    if draft is None or draft.status != "final" or not isinstance(draft.snapshot, dict):
        return None
    return draft.snapshot


async def active_adopted_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> DraftVersion | None:
    """Latest adopted draft that still re-reads Product 1 mappings."""
    await aset_rls_org_id(session, org_id)
    return (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == year_end.id,
                DraftVersion.tb_version_id.is_(None),
                DraftVersion.is_frozen.is_(False),
            )
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
    ).first()


async def ensure_adopted_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> DraftVersion:
    """Insert one null-version draft. A later continuation does not add another."""
    await aset_rls_org_id(session, org_id)
    existing = await _latest_draft(
        session, org_id=org_id, year_end_id=year_end.id
    )
    if existing is not None:
        return existing
    fingerprint = await current_mapping_fingerprint(
        session, org_id=org_id, year_end=year_end
    )
    created = DraftVersion(
        org_id=year_end.org_id,
        company_id=year_end.company_id,
        year_end_id=year_end.id,
        version_number=1,
        pack_id=year_end.pack_id,
        pack_version=year_end.pack_version,
        status="draft",
        tb_version_id=None,
        mappings_sha256=fingerprint,
        is_frozen=False,
        row_version=1,
    )
    try:
        async with session.begin_nested():
            session.add(created)
            await session.flush()
    except IntegrityError:
        found = await _latest_draft(
            session, org_id=org_id, year_end_id=year_end.id
        )
        if found is None:
            raise
        return found
    return created


async def mapping_notice_for(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
) -> str | None:
    """Notice on the active adopted draft when live mappings have moved."""
    if (
        draft.tb_version_id is not None
        or draft.is_frozen
        or draft.mappings_sha256 is None
    ):
        return None
    live = await current_mapping_fingerprint(
        session, org_id=org_id, year_end=year_end
    )
    if live == draft.mappings_sha256:
        return None
    return MAPPING_NOTICE


async def reconcile_adopted(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> ReconciliationReport:
    """Same checks as a statutory version, fed by the adopted Product 1 trial balance."""
    gate = check_prior_year_gate(year_end.prior_year_validated)
    if gate is not None:
        return build_reconciliation(
            prior_year_validated=False,
            tb_lines=[],
            mappings={},
            prior_retained_earnings=Decimal("0"),
        )
    loaded = await load_adopted_inputs(session, org_id=org_id, year_end=year_end)
    return build_reconciliation(
        prior_year_validated=True,
        tb_lines=loaded.tb_lines,
        mappings=loaded.mappings,
        prior_retained_earnings=loaded.prior_retained_earnings,
        prior_canonical=loaded.prior_canonical,
        fa_register=loaded.fa_register,
        pack_rules_path=loaded.pack_rules_path,
    )


@dataclass(frozen=True)
class SublineReviewRow:
    nominal_code: str
    account_name: str
    product1_line: str
    suggested_line: str | None
    suggestion_confidence: Decimal | None
    statutory_line: str | None
    choices: tuple[str, ...]


@dataclass(frozen=True)
class SublineChoice:
    nominal_code: str
    account_name: str
    statutory_line: str


async def review_statutory_sublines(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
) -> tuple[SublineReviewRow, ...]:
    """Rows on the seven lines, with a suggestion and the confirmed choice."""
    await aset_rls_org_id(session, org_id)
    if year_end.adopted_trial_balance_id is None:
        raise ReconciliationRejected("No confirmed trial balance is selected", 404)
    tb = await _owned_complete_tb(
        session,
        year_end=year_end,
        trial_balance_id=year_end.adopted_trial_balance_id,
    )
    mappings = await _mappings_for_company(session, year_end.company_id)
    rows: list[SublineReviewRow] = []
    ordered = sorted(
        source_accounts_from_parsed(tb.parsed_data),
        key=lambda item: (item.row_index, item.nominal_code),
    )
    for account in ordered:
        mapping = mappings.get((account.nominal_code, account.account_name))
        if mapping is None or mapping.is_ignored or not mapping.is_confirmed:
            continue
        if not needs_statutory_subline(mapping.canonical_line):
            continue
        suggested, confidence = _suggestion_fields(
            mapping.canonical_line,
            account.account_name,
            mapping.statutory_line,
        )
        stored = (mapping.statutory_line or "").strip() or None
        rows.append(
            SublineReviewRow(
                nominal_code=account.nominal_code,
                account_name=account.account_name,
                product1_line=mapping.canonical_line.strip().casefold(),
                suggested_line=suggested,
                suggestion_confidence=confidence,
                statutory_line=stored,
                choices=allowed_sublines(mapping.canonical_line),
            )
        )
    return tuple(rows)


async def confirm_statutory_sublines(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    user_id: uuid.UUID,
    choices: Sequence[SublineChoice],
) -> tuple[SublineReviewRow, ...]:
    """Store the accountant's sub-line. Does not change the Product 1 line."""
    if not choices:
        raise ReconciliationRejected("Choose a statutory sub-line")
    await aset_rls_org_id(session, org_id)
    pending = {
        (row.nominal_code, row.account_name): row
        for row in await review_statutory_sublines(
            session, org_id=org_id, year_end=year_end
        )
    }
    stored_rows = (
        await session.scalars(
            select(AccountMapping).where(
                AccountMapping.company_id == year_end.company_id
            )
        )
    ).all()
    by_key = {
        ((row.source_code or "").strip(), row.source_name.strip()): row
        for row in stored_rows
    }
    seen: set[tuple[str, str]] = set()
    changes: list[dict[str, str | None]] = []
    for choice in choices:
        key = (choice.nominal_code.strip(), choice.account_name.strip())
        if key in seen:
            raise ReconciliationRejected(f"Duplicate account {key[0]}")
        seen.add(key)
        review = pending.get(key)
        if review is None:
            raise ReconciliationRejected(
                f"Account {key[0]} {key[1]} is not waiting for a sub-line",
                404,
            )
        chosen = choice.statutory_line.strip()
        if chosen not in review.choices or chosen not in statutory_lines():
            raise ReconciliationRejected(
                f"Statutory sub-line '{chosen}' is not a home for "
                f"'{review.product1_line}'"
            )
        mapping = by_key.get(key)
        if mapping is None:
            raise ReconciliationRejected(
                f"Account {key[0]} {key[1]} is not waiting for a sub-line",
                404,
            )
        previous = mapping.statutory_line
        mapping.statutory_line = chosen
        changes.append(
            {
                "nominal_code": key[0],
                "account_name": key[1],
                "from": previous,
                "to": chosen,
            }
        )
    await session.flush()
    draft = await _latest_draft(session, org_id=org_id, year_end_id=year_end.id)
    if (
        draft is not None
        and not draft.is_frozen
        and draft.tb_version_id is None
    ):
        draft.mappings_sha256 = await current_mapping_fingerprint(
            session, org_id=org_id, year_end=year_end
        )
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="statutory_subline_confirmed",
        entity_type="year_end",
        entity_id=year_end.id,
        new_value={"lines": changes},
    )
    return await review_statutory_sublines(
        session, org_id=org_id, year_end=year_end
    )
