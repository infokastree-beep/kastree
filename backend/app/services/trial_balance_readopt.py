"""Switch the statutory period by adopting a different trial balance.

The existing adopt route stays same-period and does not change dates.
This module is the confirmed re-adopt. It does not re-pin the pack and
it does not call ``pin_pack_version`` to write a pack id.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.company import Company
from app.models.fa_version import FixedAssetLine, FixedAssetVersion
from app.models.prior_year_line import PriorYearLine
from app.models.trial_balance import TrialBalance
from app.services.adopted_trial_balance import (
    ConfirmedAccount,
    _mappings_for_company,
    carry_confirmed_accounts,
    current_mapping_fingerprint,
    source_accounts_from_parsed,
)
from app.services.audit import append_audit_log
from app.services.reconciliation import ReconciliationRejected
from findraft.engine.pack import load_manifest, pack_dir
from findraft.models.adjustments import (
    AdjustmentJournal,
    AdjustmentLine,
    DisclosureAnswer,
)
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

PERIOD_REQUIRED = "Enter a period start and period end."
PERIOD_TOO_LONG = (
    "This period is longer than 18 months. Statutory accounts will use these dates."
)
LOCK_SENTENCE = (
    "This statutory draft is final, locked, or frozen. The period cannot be changed."
)
NO_DRAFT = "There is no statutory draft for this period."
ALREADY_SELECTED = "This trial balance is already selected."
NO_PERIOD_START = "This trial balance has no period start"
ADJUSTMENTS_NOTICE = (
    "This draft's adjustments were made against a different trial balance"
)
FACE_DATES_NOTICE = (
    "The printed face dates differ from the trial balance period. "
    "Clear them in Report setup if the face should follow the trial balance."
)
COMPARATIVES_NOTICE = (
    "Comparative figures and the fixed-asset note were entered for the previous period. "
    "Review them on Prior-year comparatives, or mark the first financial period "
    "if that is still right."
)
PREVIEW_DETAIL = "Confirm the trial balance switch before it is saved."
NOTHING_TO_CONFIRM = "This draft has no adjustments to confirm."

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class ReadoptPreview(Exception):
    """``confirm`` is false. Nothing was written. The body is the preview."""

    def __init__(self, body: dict[str, object]) -> None:
        self.body = body
        super().__init__(PREVIEW_DETAIL)


def format_long_date(value: date) -> str:
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        following = date(year + 1, 1, 1)
    else:
        following = date(year, month + 1, 1)
    last = following - timedelta(days=1)
    return date(year, month, min(value.day, last.day))


def period_longer_than_18_months(period_start: date, period_end: date) -> bool:
    """True when the inclusive span passes the 18-month anniversary."""
    return period_end >= add_months(period_start, 18)


def adjustments_notice_for(draft: DraftVersion, year_end: YearEnd) -> str | None:
    basis = draft.adjustments_basis_trial_balance_id
    if basis is None or basis == year_end.adopted_trial_balance_id:
        return None
    return ADJUSTMENTS_NOTICE


def period_change_refusal(drafts: Sequence[DraftVersion]) -> str | None:
    if any(draft.status in {"final", "locked"} or draft.is_frozen for draft in drafts):
        return LOCK_SENTENCE
    return None


@dataclass(frozen=True)
class SwitchFacts:
    can_switch: bool
    switch_refusal: str | None
    adjustments_notice: str | None
    face_dates_notice: str | None
    comparatives_notice: str | None


@dataclass(frozen=True)
class ReadoptResult:
    year_end_id: uuid.UUID
    trial_balance_id: uuid.UUID
    period_start: date
    period_end: date
    draft_id: uuid.UUID
    version_number: int
    row_version: int
    adjustments_notice: str | None


@dataclass(frozen=True)
class AdjustmentsConfirmed:
    draft_id: uuid.UUID
    row_version: int
    adjustments_notice: None = None


@dataclass(frozen=True)
class CandidateRow:
    id: uuid.UUID
    period_start: date
    period_end: date
    file_name: str | None
    uploaded_at: datetime
    account_count: int | None
    currency: str | None
    ready: bool
    refusal: str | None


def _latest_draft(drafts: Sequence[DraftVersion]) -> DraftVersion | None:
    if not drafts:
        return None
    return max(drafts, key=lambda draft: draft.version_number)


async def _drafts_for(
    session: AsyncSession, *, org_id: uuid.UUID, year_end_id: uuid.UUID
) -> list[DraftVersion]:
    rows = (
        await session.scalars(
            select(DraftVersion).where(
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == year_end_id,
            )
        )
    ).all()
    return list(rows)


def _face_dates_notice(
    year_end: YearEnd, *, period_start: date | None, period_end: date | None
) -> str | None:
    setup = year_end.report_setup
    if not isinstance(setup, dict) or period_start is None or period_end is None:
        return None
    face = setup.get("face_dates")
    if not isinstance(face, dict):
        return None
    differs = False
    current_start = face.get("current_start")
    current_end = face.get("current_end")
    if isinstance(current_start, str) and current_start:
        if current_start != period_start.isoformat():
            differs = True
    if isinstance(current_end, str) and current_end:
        if current_end != period_end.isoformat():
            differs = True
    if not differs:
        return None
    return FACE_DATES_NOTICE


async def _comparatives_notice(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> str | None:
    prior = await session.scalar(
        select(PriorYearLine.id)
        .where(
            PriorYearLine.org_id == org_id,
            PriorYearLine.year_end_id == year_end.id,
        )
        .limit(1)
    )
    if prior is not None:
        return COMPARATIVES_NOTICE
    asset = await session.scalar(
        select(FixedAssetLine.id)
        .join(FixedAssetVersion, FixedAssetLine.fa_version_id == FixedAssetVersion.id)
        .where(
            FixedAssetVersion.org_id == org_id,
            FixedAssetVersion.year_end_id == year_end.id,
        )
        .limit(1)
    )
    if asset is not None:
        return COMPARATIVES_NOTICE
    return None


async def switch_facts(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    period_start: date | None,
    period_end: date | None,
) -> SwitchFacts:
    await aset_rls_org_id(session, org_id)
    drafts = await _drafts_for(session, org_id=org_id, year_end_id=year_end.id)
    refusal = period_change_refusal(drafts)
    latest = _latest_draft(drafts)
    if refusal is None and (latest is None or latest.status != "draft"):
        refusal = NO_DRAFT
    notice = None if latest is None else adjustments_notice_for(latest, year_end)
    return SwitchFacts(
        can_switch=refusal is None,
        switch_refusal=refusal,
        adjustments_notice=notice,
        face_dates_notice=_face_dates_notice(
            year_end, period_start=period_start, period_end=period_end
        ),
        comparatives_notice=await _comparatives_notice(
            session, org_id=org_id, year_end=year_end
        ),
    )


def _pack_refusal(year_end: YearEnd, period_start: date) -> str | None:
    try:
        manifest = load_manifest(
            pack_dir(year_end.pack_id, year_end.pack_version) / "pack.json"
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise ReconciliationRejected(str(exc)) from exc
    effective = manifest.get("effective_from")
    if not isinstance(effective, str) or not effective:
        return None
    effective_on = date.fromisoformat(effective)
    if period_start < effective_on:
        return (
            "This pack applies to periods beginning on or after "
            f"{format_long_date(effective_on)}. "
            f"This trial balance starts on {format_long_date(period_start)}."
        )
    return None


def _currency_refusal(tb: TrialBalance, company: Company) -> str | None:
    if tb.currency is None or not str(tb.currency).strip():
        return None
    company_code = (company.functional_currency or "GBP").strip().upper()
    tb_code = str(tb.currency).strip().upper()
    if tb_code == company_code:
        return None
    return (
        f"This trial balance is in {tb_code}. "
        f"The company reports in {company_code}. Amounts are not converted."
    )


async def _other_year_ends(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> list[YearEnd]:
    rows = (
        await session.scalars(
            select(YearEnd).where(
                YearEnd.org_id == org_id,
                YearEnd.company_id == year_end.company_id,
                YearEnd.id != year_end.id,
            )
        )
    ).all()
    return list(rows)


def _spans_overlap(other: YearEnd, start: date, end: date) -> bool:
    if other.period_start is None:
        return start <= other.period_end <= end
    return other.period_start <= end and start <= other.period_end


def _contiguity_refusal(
    year_end: YearEnd, others: Sequence[YearEnd], start: date, end: date
) -> str | None:
    for other in others:
        if other.period_end == end:
            return (
                "A statutory draft already exists for the period ending "
                f"{end.isoformat()}. Open that draft."
            )
    overlapping = [other for other in others if _spans_overlap(other, start, end)]
    if overlapping:
        named = min(overlapping, key=lambda other: other.period_end)
        return (
            "This period overlaps the statutory draft that ends on "
            f"{named.period_end.isoformat()}."
        )
    previous = [other for other in others if other.period_end < end]
    if previous:
        prior = max(previous, key=lambda other: other.period_end)
        required = prior.period_end + timedelta(days=1)
        if start != required:
            return (
                f"This trial balance starts on {start.isoformat()}. "
                f"The previous period ended on {prior.period_end.isoformat()}. "
                f"The next period must start on {required.isoformat()}."
            )
    if year_end.first_financial_period and previous:
        prior = max(previous, key=lambda other: other.period_end)
        return (
            "This draft is marked as the company's first financial period, "
            f"and another period already ends on {prior.period_end.isoformat()}."
        )
    following = [other for other in others if other.period_end > end]
    if following:
        nxt = min(following, key=lambda other: other.period_end)
        if nxt.period_start is not None:
            required = end + timedelta(days=1)
            if nxt.period_start != required:
                return (
                    f"This trial balance ends on {end.isoformat()}. "
                    f"The following period starts on {nxt.period_start.isoformat()}. "
                    f"The following period must start on {required.isoformat()}."
                )
    return None


async def _company(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> Company:
    company = await session.get(Company, year_end.company_id)
    if company is None or company.is_deleted or company.org_id != org_id:
        raise ReconciliationRejected("Trial balance not found", 404)
    return company


async def _candidate_tb(
    session: AsyncSession, *, year_end: YearEnd, trial_balance_id: uuid.UUID
) -> TrialBalance:
    tb = await session.get(TrialBalance, trial_balance_id)
    if tb is None or tb.company_id != year_end.company_id or tb.is_deleted:
        raise ReconciliationRejected("Trial balance not found", 404)
    if tb.status != "complete":
        raise ReconciliationRejected(
            "Trial balance is not a completed, confirmed Product 1 trial balance"
        )
    return tb


def _carry_refusal(
    tb: TrialBalance,
    mappings: dict[tuple[str, str], ConfirmedAccount],
) -> str | None:
    try:
        carry_confirmed_accounts(
            source_accounts_from_parsed(tb.parsed_data),
            mappings,
            require_sublines=True,
        )
    except ReconciliationRejected as exc:
        return exc.detail
    return None


def _account_count(
    tb: TrialBalance, mappings: dict[tuple[str, str], ConfirmedAccount]
) -> int | None:
    try:
        _lines, _engine, carried = carry_confirmed_accounts(
            source_accounts_from_parsed(tb.parsed_data),
            mappings,
            require_sublines=False,
        )
    except ReconciliationRejected:
        return None
    return len(carried)


async def _row_refusal(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    tb: TrialBalance,
    company: Company,
    others: Sequence[YearEnd],
    mappings: dict[tuple[str, str], ConfirmedAccount],
    year_end_block: str | None,
) -> str | None:
    if (
        year_end.adopted_trial_balance_id == tb.id
        and year_end.period_start == tb.period_start
        and year_end.period_end == tb.period_end
    ):
        return ALREADY_SELECTED
    if tb.period_start is None:
        return NO_PERIOD_START
    if year_end_block is not None:
        return year_end_block
    pack = _pack_refusal(year_end, tb.period_start)
    if pack is not None:
        return pack
    currency = _currency_refusal(tb, company)
    if currency is not None:
        return currency
    overlap = _contiguity_refusal(year_end, others, tb.period_start, tb.period_end)
    if overlap is not None:
        return overlap
    return _carry_refusal(tb, mappings)


async def list_readopt_candidates(
    session: AsyncSession, *, org_id: uuid.UUID, year_end: YearEnd
) -> list[CandidateRow]:
    await aset_rls_org_id(session, org_id)
    drafts = await _drafts_for(session, org_id=org_id, year_end_id=year_end.id)
    block = period_change_refusal(drafts)
    latest = _latest_draft(drafts)
    if block is None and (latest is None or latest.status != "draft"):
        block = NO_DRAFT
    company = await _company(session, org_id=org_id, year_end=year_end)
    others = await _other_year_ends(session, org_id=org_id, year_end=year_end)
    mappings = await _mappings_for_company(session, year_end.company_id)
    balances = (
        await session.scalars(
            select(TrialBalance)
            .where(
                TrialBalance.company_id == year_end.company_id,
                TrialBalance.is_deleted.is_(False),
                TrialBalance.status == "complete",
                TrialBalance.period_start.is_not(None),
                TrialBalance.id != year_end.adopted_trial_balance_id,
            )
            .order_by(TrialBalance.period_end.desc(), TrialBalance.created_at.desc())
        )
    ).all()
    rows: list[CandidateRow] = []
    for tb in balances:
        if tb.period_start is None:
            continue
        refusal = await _row_refusal(
            session,
            org_id=org_id,
            year_end=year_end,
            tb=tb,
            company=company,
            others=others,
            mappings=mappings,
            year_end_block=block,
        )
        rows.append(
            CandidateRow(
                id=tb.id,
                period_start=tb.period_start,
                period_end=tb.period_end,
                file_name=tb.original_filename,
                uploaded_at=tb.created_at,
                account_count=_account_count(tb, mappings),
                currency=tb.currency,
                ready=refusal is None,
                refusal=refusal,
            )
        )
    return rows


async def _journals(
    session: AsyncSession, *, org_id: uuid.UUID, draft_id: uuid.UUID
) -> list[AdjustmentJournal]:
    rows = (
        await session.scalars(
            select(AdjustmentJournal)
            .where(
                AdjustmentJournal.org_id == org_id,
                AdjustmentJournal.draft_version_id == draft_id,
            )
            .order_by(AdjustmentJournal.created_at.asc(), AdjustmentJournal.id.asc())
        )
    ).all()
    return list(rows)


async def _journal_lines(
    session: AsyncSession, *, org_id: uuid.UUID, journal_id: uuid.UUID
) -> list[AdjustmentLine]:
    rows = (
        await session.scalars(
            select(AdjustmentLine)
            .where(
                AdjustmentLine.org_id == org_id,
                AdjustmentLine.journal_id == journal_id,
            )
            .order_by(AdjustmentLine.line_no.asc())
        )
    ).all()
    return list(rows)


def _present_accounts(tb: TrialBalance) -> set[tuple[str, str]]:
    return {
        (account.nominal_code.strip(), account.account_name.strip())
        for account in source_accounts_from_parsed(tb.parsed_data)
    }


async def _preview_body(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    draft: DraftVersion,
    tb: TrialBalance,
) -> dict[str, object]:
    present = _present_accounts(tb)
    journals: list[dict[str, object]] = []
    for journal in await _journals(session, org_id=org_id, draft_id=draft.id):
        lines = []
        for line in await _journal_lines(session, org_id=org_id, journal_id=journal.id):
            lines.append(
                {
                    "nominal_code": line.nominal_code,
                    "account_name": line.account_name,
                    "present": (
                        line.nominal_code.strip(),
                        line.account_name.strip(),
                    )
                    in present,
                }
            )
        journals.append({"narration": journal.narration, "lines": lines})
    answers = (
        await session.scalars(
            select(DisclosureAnswer).where(
                DisclosureAnswer.org_id == org_id,
                DisclosureAnswer.draft_version_id == draft.id,
            )
        )
    ).all()
    return {
        "detail": PREVIEW_DETAIL,
        "period_start": tb.period_start.isoformat() if tb.period_start else None,
        "period_end": tb.period_end.isoformat(),
        "journals": journals,
        "disclosure_answer_count": len(answers),
        "note_library_stored": draft.note_library is not None,
        "draft_id": str(draft.id),
        "version_number": draft.version_number,
    }


def _active_draft(drafts: Sequence[DraftVersion], row_version: int) -> DraftVersion:
    refusal = period_change_refusal(drafts)
    if refusal is not None:
        raise ReconciliationRejected(refusal, 409)
    latest = _latest_draft(drafts)
    if latest is None or latest.status != "draft" or latest.is_frozen:
        raise ReconciliationRejected(NO_DRAFT, 409)
    if latest.row_version != row_version:
        raise ReconciliationRejected("row_version does not match", 409)
    return latest


async def readopt_trial_balance(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    trial_balance_id: uuid.UUID,
    row_version: int,
    confirm: bool,
) -> ReadoptResult:
    """Preview or switch. A refusal leaves every stored row unchanged."""
    await aset_rls_org_id(session, org_id)
    tb = await _candidate_tb(
        session, year_end=year_end, trial_balance_id=trial_balance_id
    )
    if (
        year_end.adopted_trial_balance_id == tb.id
        and year_end.period_start == tb.period_start
        and year_end.period_end == tb.period_end
    ):
        raise ReconciliationRejected(ALREADY_SELECTED, 422)
    if tb.period_start is None:
        raise ReconciliationRejected(NO_PERIOD_START, 422)
    drafts = await _drafts_for(session, org_id=org_id, year_end_id=year_end.id)
    draft = _active_draft(drafts, row_version)
    pack = _pack_refusal(year_end, tb.period_start)
    if pack is not None:
        raise ReconciliationRejected(pack, 422)
    company = await _company(session, org_id=org_id, year_end=year_end)
    currency = _currency_refusal(tb, company)
    if currency is not None:
        raise ReconciliationRejected(currency, 422)
    others = await _other_year_ends(session, org_id=org_id, year_end=year_end)
    overlap = _contiguity_refusal(year_end, others, tb.period_start, tb.period_end)
    if overlap is not None:
        raise ReconciliationRejected(overlap, 409)
    mappings = await _mappings_for_company(session, year_end.company_id)
    carry = _carry_refusal(tb, mappings)
    if carry is not None:
        raise ReconciliationRejected(carry, 422)
    if not confirm:
        raise ReadoptPreview(
            await _preview_body(session, org_id=org_id, draft=draft, tb=tb)
        )

    previous_tb = year_end.adopted_trial_balance_id
    old_value: dict[str, object] = {
        "adopted_trial_balance_id": None if previous_tb is None else str(previous_tb),
        "period_start": (
            None if year_end.period_start is None else year_end.period_start.isoformat()
        ),
        "period_end": year_end.period_end.isoformat(),
    }
    year_end.adopted_trial_balance_id = tb.id
    year_end.period_start = tb.period_start
    year_end.period_end = tb.period_end
    journals = await _journals(session, org_id=org_id, draft_id=draft.id)
    if journals:
        draft.adjustments_basis_trial_balance_id = previous_tb
    else:
        draft.adjustments_basis_trial_balance_id = None
    draft.mappings_sha256 = await current_mapping_fingerprint(
        session, org_id=org_id, year_end=year_end
    )
    draft.row_version = row_version + 1
    new_value: dict[str, object] = {
        "adopted_trial_balance_id": str(tb.id),
        "period_start": tb.period_start.isoformat(),
        "period_end": tb.period_end.isoformat(),
        "draft_id": str(draft.id),
    }
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="trial_balance_readopted",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=old_value,
        new_value=new_value,
    )
    await session.flush()
    return ReadoptResult(
        year_end_id=year_end.id,
        trial_balance_id=tb.id,
        period_start=tb.period_start,
        period_end=tb.period_end,
        draft_id=draft.id,
        version_number=draft.version_number,
        row_version=draft.row_version,
        adjustments_notice=adjustments_notice_for(draft, year_end),
    )


async def confirm_adjustments(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    year_end: YearEnd,
    row_version: int,
) -> AdjustmentsConfirmed:
    """Record that the journals were reviewed against the trial balance now adopted."""
    await aset_rls_org_id(session, org_id)
    drafts = await _drafts_for(session, org_id=org_id, year_end_id=year_end.id)
    draft = _active_draft(drafts, row_version)
    current = year_end.adopted_trial_balance_id
    previous = draft.adjustments_basis_trial_balance_id
    if current is None or previous is None or previous == current:
        raise ReconciliationRejected(NOTHING_TO_CONFIRM, 422)
    draft.adjustments_basis_trial_balance_id = current
    draft.row_version = row_version + 1
    confirmed_old: dict[str, object] = {
        "adjustments_basis_trial_balance_id": str(previous)
    }
    confirmed_new: dict[str, object] = {
        "year_end_id": str(year_end.id),
        "draft_id": str(draft.id),
        "previous_trial_balance_id": str(previous),
        "current_trial_balance_id": str(current),
    }
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="adjustments_reconfirmed",
        entity_type="year_end",
        entity_id=year_end.id,
        old_value=confirmed_old,
        new_value=confirmed_new,
    )
    await session.flush()
    return AdjustmentsConfirmed(
        draft_id=draft.id,
        row_version=draft.row_version,
        adjustments_notice=None,
    )
