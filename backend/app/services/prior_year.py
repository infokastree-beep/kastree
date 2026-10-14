"""Prior-year comparatives: four sources, one stored column.

Python Decimal is the only arithmetic. The printed column is the snapshot
taken at confirm. A later edit of the source does not move it.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.company import Company
from app.models.financial_statement import FinancialStatement
from app.models.prior_year_line import PriorYearLine
from app.models.statement_line_item import StatementLineItem
from app.models.trial_balance import TrialBalance
from app.schemas.report_setup import ReportSetupWrite
from app.services.adopted_trial_balance import (
    CarriedMapping,
    ConfirmedAccount,
    _mappings_for_company,
    carry_confirmed_accounts,
    engine_line_for_confirmed_mapping,
    source_accounts_from_parsed,
)
from app.services.audit import append_audit_log
from app.services.reconciliation import ReconciliationRejected
from app.services.report_setup import default_report_setup
from findraft.engine.lines import CONSUMED, FIXED_ASSETS
from findraft.engine.mapping import aggregate
from findraft.engine.money import D, money
from findraft.engine.reconciliation import (
    check_bs_balances,
    check_fa_rollforward,
    check_prior_year_gate,
    check_re_rollforward,
)
from findraft.engine.statements import build_sofp
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

FILED_ACCOUNTS = "Confirm that these figures match last year's filed accounts."
MANUAL_BLOCKED = "A prior trial balance is available. Confirm that source."
MAPPING_CONFIRM = (
    "Confirm the accounts whose mapping differs from the previous period's statements."
)
STALE_NOTICE = (
    "The prior trial balance has changed since these comparatives were confirmed."
)
LATER_FINAL = (
    "A later final snapshot exists for the previous period. "
    "These comparatives stay as confirmed until you confirm again."
)
FACE_DATE_NOTICE = (
    "The printed prior dates differ from the comparative period. "
    "Clear them in Report setup if the face should follow the source."
)
FIRST_PERIOD_GUIDANCE = (
    "Choose this when the company has no earlier accounting period. "
    "The accounts will not show a comparative column. "
    "You can undo this until the draft is final."
)
FIRST_PERIOD_STATEMENT = (
    "This is the company's first financial period. "
    "Comparative amounts are not presented."
)
UNDO_CLOSED = (
    "This statutory draft is final, locked, or frozen. "
    "The first-period choice cannot be undone."
)
OTHER_PERIOD = (
    "This draft is marked as the company's first financial period, "
    "and another period already ends on {previous_end}."
)
NO_FINAL = "No final snapshot is available for the previous period."

_SOURCES = ("product1_tb", "first_period", "manual", "final_snapshot")


class PriorYearRejected(Exception):
    def __init__(self, detail: str | dict[str, object], status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        text = detail if isinstance(detail, str) else str(detail.get("message", ""))
        super().__init__(text)


@dataclass(frozen=True)
class MappingDifference:
    account_code: str
    account_name: str
    previous_line: str
    current_line: str


@dataclass(frozen=True)
class SourcePreview:
    kind: str
    preferred: bool
    available: bool
    refusal: str | None
    guidance: str | None
    trial_balance_id: uuid.UUID | None
    year_end_id: uuid.UUID | None
    draft_id: uuid.UUID | None
    period_start: date | None
    period_end: date | None
    lines: tuple[tuple[str, Decimal], ...]
    mapping_differences: tuple[MappingDifference, ...]
    checks: tuple[tuple[str, bool | None, str], ...]


@dataclass(frozen=True)
class PriorYearView:
    year_end_id: uuid.UUID
    prior_year_validated: bool
    first_financial_period: bool
    comparative_source: str | None
    stored_lines: tuple[tuple[str, Decimal], ...]
    stale_notice: str | None
    face_date_notice: str | None
    sources: tuple[SourcePreview, ...]


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


def _lines_sha(lines: dict[str, Decimal]) -> str:
    rows = [
        {"amount": format(amount, "f"), "canonical_line": name}
        for name, amount in sorted(lines.items())
    ]
    encoded = json.dumps(rows, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _pair(lines: dict[str, Decimal]) -> tuple[tuple[str, Decimal], ...]:
    return tuple(sorted(lines.items()))


def _face(sofp: dict[str, object], label: str) -> Decimal:
    rows = sofp.get("rows")
    if not isinstance(rows, list):
        raise PriorYearRejected("Balance sheet rows are missing", 422)
    for item in rows:
        if isinstance(item, tuple) and len(item) >= 2 and item[0] == label:
            current = item[1]
            if isinstance(current, Decimal):
                return current
    raise PriorYearRejected(f"Balance sheet row missing: {label}", 422)


def manual_column_message(lines: dict[str, Decimal]) -> str | None:
    """The engine message when a manual column cannot be stored."""
    try:
        sofp = build_sofp(lines, {})
    except ValueError as exc:
        return str(exc)
    balance = check_bs_balances(sofp)
    if not balance.passed:
        return balance.message
    if any(lines.get(name, Decimal("0")) != 0 for name in FIXED_ASSETS):
        closing = money(
            _face(sofp, "Tangible assets")
            + _face(sofp, "Intangible assets")
            + _face(sofp, "Fixed asset investments")
        )
        rolled = check_fa_rollforward(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), closing
        )
        if not rolled.passed:
            return rolled.message
    profit = sofp.get("profit")
    if not isinstance(profit, Decimal):
        return "Retained earnings could not be checked"
    dividends = money(lines.get("DIVIDENDS", Decimal("0")))
    entered = money(-lines.get("RETAINED_EARNINGS", Decimal("0")))
    face = _face(sofp, "Profit and loss account")
    if profit == 0 and dividends == 0:
        opening = entered
        closing_re = face
    else:
        opening = Decimal("0")
        closing_re = entered
    rolled_re = check_re_rollforward(opening, profit, dividends, closing_re)
    if not rolled_re.passed:
        return rolled_re.message
    return None


def _prepare_lines(lines: list[tuple[str, str]]) -> dict[str, Decimal]:
    if not lines:
        raise PriorYearRejected("Prior-year entry needs at least one canonical line")
    prepared: dict[str, Decimal] = {}
    for name, raw_amount in lines:
        if name not in CONSUMED:
            raise PriorYearRejected(f"Unknown canonical line: {name}")
        if name in prepared:
            raise PriorYearRejected(f"Duplicate canonical line: {name}")
        prepared[name] = canonical_amount(raw_amount)
    kept = {name: amount for name, amount in prepared.items() if amount != 0}
    if not kept:
        raise PriorYearRejected("Prior-year entry needs at least one canonical line")
    return kept


async def _stored_lines(
    session: AsyncSession, year_end_id: uuid.UUID
) -> dict[str, Decimal]:
    rows = (
        await session.scalars(
            select(PriorYearLine).where(PriorYearLine.year_end_id == year_end_id)
        )
    ).all()
    return {row.canonical_line: row.amount for row in rows}


async def _replace_lines(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    totals: dict[str, Decimal],
) -> list[PriorYearLine]:
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
    for name, amount in sorted(totals.items()):
        row = PriorYearLine(
            org_id=year_end.org_id,
            company_id=year_end.company_id,
            year_end_id=year_end.id,
            canonical_line=name,
            amount=amount,
        )
        session.add(row)
        stored.append(row)
    await session.flush()
    return stored


def _clear_source(year_end: YearEnd) -> None:
    year_end.comparative_source = None
    year_end.comparative_source_trial_balance_id = None
    year_end.comparative_source_year_end_id = None
    year_end.comparative_source_draft_id = None
    year_end.comparative_source_sha256 = None


async def _audit(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    action: str,
    year_end_id: uuid.UUID,
    new_value: dict[str, object],
) -> None:
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action=action,
        entity_type="year_end",
        entity_id=year_end_id,
        new_value=new_value,
    )


def _refuse_first_period(year_end: YearEnd) -> None:
    if year_end.first_financial_period:
        raise PriorYearRejected("This year end is a first financial period", 409)


async def _other_period_end(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> date | None:
    other = await session.scalar(
        select(YearEnd.period_end)
        .where(
            YearEnd.org_id == org_id,
            YearEnd.company_id == year_end.company_id,
            YearEnd.id != year_end.id,
        )
        .order_by(YearEnd.period_end.desc())
        .limit(1)
    )
    return other


async def _any_closed_draft(
    session: AsyncSession, *, org_id: uuid.UUID, year_end_id: uuid.UUID
) -> bool:
    drafts = (
        await session.scalars(
            select(DraftVersion).where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == year_end_id,
            )
        )
    ).all()
    return any(
        draft.status in {"final", "locked"} or draft.is_frozen for draft in drafts
    )


def _expected_prior_end(year_end: YearEnd) -> date | None:
    if year_end.period_start is None:
        return None
    return year_end.period_start - timedelta(days=1)


async def _complete_tb(
    session: AsyncSession, *, company_id: uuid.UUID, period_end: date
) -> TrialBalance | None:
    row = await session.scalar(
        select(TrialBalance).where(
            TrialBalance.company_id == company_id,
            TrialBalance.period_end == period_end,
            TrialBalance.status == "complete",
            TrialBalance.is_deleted.is_(False),
        )
    )
    return row if isinstance(row, TrialBalance) else None


async def _nearest_earlier_tb(
    session: AsyncSession, *, company_id: uuid.UUID, period_start: date
) -> TrialBalance | None:
    row = await session.scalar(
        select(TrialBalance)
        .where(
            TrialBalance.company_id == company_id,
            TrialBalance.period_end < period_start,
            TrialBalance.status == "complete",
            TrialBalance.is_deleted.is_(False),
        )
        .order_by(TrialBalance.period_end.desc())
        .limit(1)
    )
    return row if isinstance(row, TrialBalance) else None


def _translate(
    tb: TrialBalance,
    mappings: dict[tuple[str, str], ConfirmedAccount],
) -> tuple[dict[str, Decimal], tuple[CarriedMapping, ...]] | str:
    try:
        accounts = source_accounts_from_parsed(tb.parsed_data)
        tb_lines, engine_by_code, carried = carry_confirmed_accounts(accounts, mappings)
    except ReconciliationRejected as exc:
        return exc.detail
    aggregated = aggregate(tb_lines, engine_by_code)
    totals = {
        name: money(amount)
        for name, amount in aggregated.items()
        if isinstance(amount, Decimal) and amount != 0
    }
    return totals, carried


async def _statement_lines_for_tb(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    tb: TrialBalance,
) -> dict[tuple[str, str], str] | None:
    """Account (code, name) to the engine line on the previous statements.

    None means the previous period has no statements.
    """
    previous = await session.scalar(
        select(YearEnd).where(
            YearEnd.org_id == org_id,
            YearEnd.company_id == company_id,
            YearEnd.period_end == tb.period_end,
        )
    )
    if previous is not None:
        draft = await session.scalar(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == previous.id,
                DraftVersion.status == "final",
            )
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
        if draft is not None:
            frozen = draft.frozen_inputs
            if isinstance(frozen, dict):
                raw_lines = frozen.get("tb_lines")
                raw_mappings = frozen.get("mappings")
                if isinstance(raw_lines, list) and isinstance(raw_mappings, dict):
                    found: dict[tuple[str, str], str] = {}
                    for item in raw_lines:
                        if not isinstance(item, dict):
                            continue
                        code = item.get("nominal_code")
                        name = item.get("account_name")
                        if not isinstance(code, str) or not isinstance(name, str):
                            continue
                        engine = raw_mappings.get(code)
                        if isinstance(engine, str) and engine:
                            found[(code, name)] = engine
                    return found
            if isinstance(draft.snapshot, dict):
                return {}
    statements = (
        await session.scalars(
            select(FinancialStatement).where(FinancialStatement.tb_id == tb.id)
        )
    ).all()
    if not statements:
        return None
    found_product: dict[tuple[str, str], str] = {}
    for statement in statements:
        items = (
            await session.scalars(
                select(StatementLineItem).where(
                    StatementLineItem.statement_id == statement.id,
                    StatementLineItem.is_subtotal.is_(False),
                )
            )
        ).all()
        for item in items:
            mapping_ids = list(item.source_account_ids or [])
            if not mapping_ids:
                continue
            mappings = (
                await session.scalars(
                    select(AccountMapping).where(AccountMapping.id.in_(mapping_ids))
                )
            ).all()
            for mapping in mappings:
                code = (mapping.source_code or "").strip()
                name = mapping.source_name.strip()
                if not code or not name:
                    continue
                try:
                    engine = engine_line_for_confirmed_mapping(
                        item.line_item_code, name, mapping.statutory_line
                    )
                except ReconciliationRejected:
                    continue
                found_product[(code, name)] = engine
    return found_product


def _differences(
    carried: tuple[CarriedMapping, ...],
    previous: dict[tuple[str, str], str] | None,
) -> tuple[MappingDifference, ...]:
    if not previous:
        return ()
    rows: list[MappingDifference] = []
    for item in carried:
        current = item.canonical_line
        if current is None:
            continue
        prior = previous.get((item.nominal_code, item.account_name))
        if prior is None or prior == current:
            continue
        rows.append(
            MappingDifference(
                account_code=item.nominal_code,
                account_name=item.account_name,
                previous_line=prior,
                current_line=current,
            )
        )
    rows.sort(key=lambda row: (row.account_code, row.account_name))
    return tuple(rows)


async def _previous_final(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> tuple[YearEnd, DraftVersion, dict[str, Decimal]] | None:
    expected = _expected_prior_end(year_end)
    if expected is None:
        return None
    previous = await session.scalar(
        select(YearEnd).where(
            YearEnd.org_id == org_id,
            YearEnd.company_id == year_end.company_id,
            YearEnd.period_end == expected,
        )
    )
    if previous is None:
        return None
    drafts = (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == previous.id,
                DraftVersion.status == "final",
            )
            .order_by(DraftVersion.version_number.desc())
        )
    ).all()
    for draft in drafts:
        snapshot = draft.snapshot
        if not isinstance(snapshot, dict):
            continue
        raw = snapshot.get("canonical_current")
        if not isinstance(raw, dict):
            continue
        totals: dict[str, Decimal] = {}
        for key, value in raw.items():
            if not isinstance(key, str) or key not in CONSUMED:
                continue
            if not isinstance(value, str):
                continue
            amount = canonical_amount(value)
            if amount != 0:
                totals[key] = amount
        return previous, draft, totals
    return None


def _face_pair(year_end: YearEnd) -> tuple[str | None, str | None]:
    setup = year_end.report_setup
    if not isinstance(setup, dict):
        return None, None
    face = setup.get("face_dates")
    if not isinstance(face, dict):
        return None, None
    start = face.get("prior_start")
    end = face.get("prior_end")
    prior_start = start if isinstance(start, str) and start else None
    prior_end = end if isinstance(end, str) and end else None
    return prior_start, prior_end


def _face_notice(
    year_end: YearEnd, period_start: date | None, period_end: date | None
) -> str | None:
    if period_start is None or period_end is None:
        return None
    stored_start, stored_end = _face_pair(year_end)
    if stored_start is None and stored_end is None:
        return None
    if (
        stored_start == period_start.isoformat()
        and stored_end == period_end.isoformat()
    ):
        return None
    return FACE_DATE_NOTICE


def _fill_face_dates(
    year_end: YearEnd,
    period_start: date | None,
    period_end: date | None,
    *,
    currency: str,
) -> str | None:
    """Fill empty prior face dates from the source. A saved pair is left as set.

    The stored document stays a complete report setup. Display defaults are
    written only when nothing has been saved yet.
    """
    if period_start is None or period_end is None:
        return None
    stored_start, stored_end = _face_pair(year_end)
    source_start = period_start.isoformat()
    source_end = period_end.isoformat()
    if stored_start is None and stored_end is None:
        raw = year_end.report_setup
        write: ReportSetupWrite
        if isinstance(raw, dict) and raw:
            try:
                write = ReportSetupWrite.model_validate(raw)
            except ValidationError:
                write = default_report_setup(year_end, currency)
        else:
            write = default_report_setup(year_end, currency)
        face = write.face_dates.model_copy(
            update={"prior_start": period_start, "prior_end": period_end}
        )
        year_end.report_setup = write.model_copy(
            update={"face_dates": face}
        ).model_dump(mode="json")
        return None
    if stored_start != source_start or stored_end != source_end:
        return FACE_DATE_NOTICE
    return None


async def _functional_currency(
    session: AsyncSession, *, org_id: uuid.UUID, company_id: uuid.UUID
) -> str:
    code = await session.scalar(
        select(Company.functional_currency).where(
            Company.id == company_id,
            Company.org_id == org_id,
        )
    )
    if not isinstance(code, str) or not code.strip():
        return "GBP"
    return code.strip().upper()


def _manual_checks() -> tuple[tuple[str, bool | None, str], ...]:
    return (
        ("V-BS-001", None, "The column must balance."),
        ("V-RE-001", None, "Retained earnings must roll forward."),
        (
            "V-FA-001",
            None,
            "A fixed-asset line must roll forward.",
        ),
    )


async def read_prior_year(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> PriorYearView:
    await aset_rls_org_id(session, org_id)
    mappings = await _mappings_for_company(session, year_end.company_id)
    expected = _expected_prior_end(year_end)
    tb: TrialBalance | None = None
    tb_refusal: str | None = None
    tb_available = False
    totals: dict[str, Decimal] = {}
    differences: tuple[MappingDifference, ...] = ()
    if year_end.period_start is None:
        tb_refusal = (
            "This year end has no period start, so a prior trial balance "
            "cannot be matched."
        )
    elif expected is not None:
        tb = await _complete_tb(
            session, company_id=year_end.company_id, period_end=expected
        )
        if tb is None:
            earlier = await _nearest_earlier_tb(
                session,
                company_id=year_end.company_id,
                period_start=year_end.period_start,
            )
            if earlier is not None:
                tb = earlier
                tb_refusal = (
                    f"This trial balance ends on {earlier.period_end.isoformat()}. "
                    f"This period starts on {year_end.period_start.isoformat()}. "
                    "The prior period must end the day before."
                )
        else:
            translated = _translate(tb, mappings)
            if isinstance(translated, str):
                tb_refusal = translated
            else:
                totals, carried = translated
                previous = await _statement_lines_for_tb(
                    session,
                    org_id=org_id,
                    company_id=year_end.company_id,
                    tb=tb,
                )
                differences = _differences(carried, previous)
                tb_available = True
    final = await _previous_final(session, org_id=org_id, year_end=year_end)
    other_end = await _other_period_end(session, org_id=org_id, year_end=year_end)
    first_available = other_end is None
    first_refusal = None
    if other_end is not None and not year_end.first_financial_period:
        first_refusal = OTHER_PERIOD.format(previous_end=other_end.isoformat())
        first_available = False
    manual_available = tb is None and year_end.period_start is not None
    manual_refusal = MANUAL_BLOCKED if tb is not None else None
    if year_end.period_start is None:
        manual_available = False
        manual_refusal = tb_refusal
    product_ok = tb_available and tb_refusal is None
    if product_ok:
        preferred = "product1_tb"
    elif first_available:
        preferred = "first_period"
    elif manual_available:
        preferred = "manual"
    elif final is not None:
        preferred = "final_snapshot"
    else:
        preferred = "first_period"
    stored = await _stored_lines(session, year_end.id)
    stale: str | None = None
    if (
        year_end.comparative_source == "product1_tb"
        and year_end.comparative_source_sha256
        and (
            not tb_available
            or tb is None
            or tb.id != year_end.comparative_source_trial_balance_id
            or _lines_sha(totals) != year_end.comparative_source_sha256
        )
    ):
        stale = STALE_NOTICE
    later: str | None = None
    if year_end.comparative_source == "final_snapshot" and final is not None:
        _previous, latest, _totals = final
        if latest.id != year_end.comparative_source_draft_id:
            later = LATER_FINAL
    notice_start: date | None = None
    notice_end: date | None = None
    if year_end.comparative_source == "product1_tb" and tb is not None:
        notice_start, notice_end = tb.period_start, tb.period_end
    elif year_end.comparative_source == "final_snapshot" and final is not None:
        notice_start = final[0].period_start
        notice_end = final[0].period_end
    face_notice = _face_notice(year_end, notice_start, notice_end)
    sources = (
        SourcePreview(
            kind="product1_tb",
            preferred=preferred == "product1_tb",
            available=product_ok,
            refusal=tb_refusal,
            guidance=None,
            trial_balance_id=None if tb is None or not product_ok else tb.id,
            year_end_id=None,
            draft_id=None,
            period_start=None if tb is None else tb.period_start,
            period_end=None if tb is None else tb.period_end,
            lines=_pair(totals) if product_ok else (),
            mapping_differences=differences if product_ok else (),
            checks=(),
        ),
        SourcePreview(
            kind="first_period",
            preferred=preferred == "first_period",
            available=first_available or year_end.first_financial_period,
            refusal=first_refusal,
            guidance=FIRST_PERIOD_GUIDANCE,
            trial_balance_id=None,
            year_end_id=None,
            draft_id=None,
            period_start=None,
            period_end=None,
            lines=(),
            mapping_differences=(),
            checks=(),
        ),
        SourcePreview(
            kind="manual",
            preferred=preferred == "manual",
            available=manual_available,
            refusal=manual_refusal,
            guidance=None,
            trial_balance_id=None,
            year_end_id=None,
            draft_id=None,
            period_start=None,
            period_end=None,
            lines=(),
            mapping_differences=(),
            checks=_manual_checks(),
        ),
        SourcePreview(
            kind="final_snapshot",
            preferred=preferred == "final_snapshot",
            available=final is not None,
            refusal=None if final is not None else NO_FINAL,
            guidance=None,
            trial_balance_id=None,
            year_end_id=None if final is None else final[0].id,
            draft_id=None if final is None else final[1].id,
            period_start=None if final is None else final[0].period_start,
            period_end=None if final is None else final[0].period_end,
            lines=() if final is None else _pair(final[2]),
            mapping_differences=(),
            checks=(),
        ),
    )
    shown_stale = stale if year_end.comparative_source == "product1_tb" else None
    if year_end.comparative_source == "final_snapshot":
        shown_stale = later
    return PriorYearView(
        year_end_id=year_end.id,
        prior_year_validated=year_end.prior_year_validated,
        first_financial_period=year_end.first_financial_period,
        comparative_source=year_end.comparative_source
        if year_end.comparative_source in _SOURCES
        else None,
        stored_lines=_pair(stored),
        stale_notice=shown_stale,
        face_date_notice=face_notice,
        sources=sources,
    )


async def confirm_prior_year(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    lines: list[tuple[str, str]],
    matches_filed_accounts: bool | None,
) -> list[PriorYearLine]:
    _refuse_first_period(year_end)
    prepared = _prepare_lines(lines)
    await aset_rls_org_id(session, org_id)
    expected = _expected_prior_end(year_end)
    if expected is not None:
        existing_tb = await _complete_tb(
            session, company_id=year_end.company_id, period_end=expected
        )
        if existing_tb is not None:
            raise PriorYearRejected(MANUAL_BLOCKED, 422)
    if year_end.period_start is not None:
        earlier = await _nearest_earlier_tb(
            session,
            company_id=year_end.company_id,
            period_start=year_end.period_start,
        )
        if earlier is not None and (expected is None or earlier.period_end != expected):
            raise PriorYearRejected(MANUAL_BLOCKED, 422)
    if matches_filed_accounts is not True:
        raise PriorYearRejected(FILED_ACCOUNTS, 422)
    message = manual_column_message(prepared)
    if message is not None:
        raise PriorYearRejected(message, 422)
    replacing = year_end.prior_year_validated
    stored = await _replace_lines(
        session, org_id=org_id, year_end=year_end, totals=prepared
    )
    _clear_source(year_end)
    year_end.comparative_source = "manual"
    year_end.comparative_source_sha256 = _lines_sha(prepared)
    year_end.prior_year_validated = True
    year_end.first_financial_period = False
    await _audit(
        session,
        org_id=org_id,
        user_id=user_id,
        action="prior_year_replaced" if replacing else "prior_year_confirmed",
        year_end_id=year_end.id,
        new_value={"year_end_id": str(year_end.id), "source": "manual"},
    )
    await session.flush()
    return stored


async def confirm_from_trial_balance(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    confirm: bool,
    mapping_differences_confirmed: bool,
) -> PriorYearView:
    _refuse_first_period(year_end)
    view = await read_prior_year(session, org_id=org_id, year_end=year_end)
    source = next(item for item in view.sources if item.kind == "product1_tb")
    if not confirm:
        return view
    if source.refusal is not None or not source.available:
        raise PriorYearRejected(
            source.refusal or "No prior trial balance is available.", 422
        )
    if source.mapping_differences and not mapping_differences_confirmed:
        raise PriorYearRejected(
            {
                "message": MAPPING_CONFIRM,
                "mapping_differences": [
                    {
                        "account_code": row.account_code,
                        "account_name": row.account_name,
                        "previous_line": row.previous_line,
                        "current_line": row.current_line,
                    }
                    for row in source.mapping_differences
                ],
            },
            422,
        )
    totals = dict(source.lines)
    if source.trial_balance_id is None:
        raise PriorYearRejected("No prior trial balance is available.", 422)
    replacing = year_end.prior_year_validated
    await _replace_lines(session, org_id=org_id, year_end=year_end, totals=totals)
    _clear_source(year_end)
    year_end.comparative_source = "product1_tb"
    year_end.comparative_source_trial_balance_id = source.trial_balance_id
    year_end.comparative_source_sha256 = _lines_sha(totals)
    year_end.prior_year_validated = True
    year_end.first_financial_period = False
    currency = await _functional_currency(
        session, org_id=org_id, company_id=year_end.company_id
    )
    _fill_face_dates(
        year_end, source.period_start, source.period_end, currency=currency
    )
    await _audit(
        session,
        org_id=org_id,
        user_id=user_id,
        action="prior_year_replaced" if replacing else "prior_year_confirmed",
        year_end_id=year_end.id,
        new_value={
            "year_end_id": str(year_end.id),
            "source": "product1_tb",
            "trial_balance_id": str(source.trial_balance_id),
        },
    )
    await session.flush()
    return await read_prior_year(session, org_id=org_id, year_end=year_end)


async def confirm_from_final(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    confirm: bool,
) -> PriorYearView:
    _refuse_first_period(year_end)
    if not confirm:
        return await read_prior_year(session, org_id=org_id, year_end=year_end)
    found = await _previous_final(session, org_id=org_id, year_end=year_end)
    if found is None:
        raise PriorYearRejected(NO_FINAL, 422)
    previous, draft, totals = found
    replacing = year_end.prior_year_validated
    await _replace_lines(session, org_id=org_id, year_end=year_end, totals=totals)
    _clear_source(year_end)
    year_end.comparative_source = "final_snapshot"
    year_end.comparative_source_year_end_id = previous.id
    year_end.comparative_source_draft_id = draft.id
    year_end.comparative_source_sha256 = _lines_sha(totals)
    year_end.prior_year_validated = True
    year_end.first_financial_period = False
    currency = await _functional_currency(
        session, org_id=org_id, company_id=year_end.company_id
    )
    _fill_face_dates(
        year_end, previous.period_start, previous.period_end, currency=currency
    )
    await _audit(
        session,
        org_id=org_id,
        user_id=user_id,
        action="prior_year_replaced" if replacing else "prior_year_confirmed",
        year_end_id=year_end.id,
        new_value={
            "year_end_id": str(year_end.id),
            "source": "final_snapshot",
            "previous_year_end_id": str(previous.id),
            "draft_id": str(draft.id),
        },
    )
    await session.flush()
    return await read_prior_year(session, org_id=org_id, year_end=year_end)


async def mark_first_financial_period(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
) -> YearEnd:
    if year_end.first_financial_period and year_end.prior_year_validated:
        raise PriorYearRejected("Prior year is already validated", 409)
    await aset_rls_org_id(session, org_id)
    other = await _other_period_end(session, org_id=org_id, year_end=year_end)
    if other is not None:
        raise PriorYearRejected(
            OTHER_PERIOD.format(previous_end=other.isoformat()), 409
        )
    await _replace_lines(session, org_id=org_id, year_end=year_end, totals={})
    _clear_source(year_end)
    year_end.comparative_source = "first_period"
    year_end.first_financial_period = True
    year_end.prior_year_validated = True
    await _audit(
        session,
        org_id=org_id,
        user_id=user_id,
        action="first_financial_period_marked",
        year_end_id=year_end.id,
        new_value={"year_end_id": str(year_end.id)},
    )
    await session.flush()
    return year_end


async def undo_first_financial_period(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
) -> YearEnd:
    await aset_rls_org_id(session, org_id)
    if await _any_closed_draft(session, org_id=org_id, year_end_id=year_end.id):
        raise PriorYearRejected(UNDO_CLOSED, 409)
    if not year_end.first_financial_period:
        raise PriorYearRejected(
            "This year end is not marked as a first financial period", 409
        )
    await _replace_lines(session, org_id=org_id, year_end=year_end, totals={})
    _clear_source(year_end)
    year_end.first_financial_period = False
    year_end.prior_year_validated = False
    await _audit(
        session,
        org_id=org_id,
        user_id=user_id,
        action="first_financial_period_cleared",
        year_end_id=year_end.id,
        new_value={"year_end_id": str(year_end.id)},
    )
    await session.flush()
    return year_end
