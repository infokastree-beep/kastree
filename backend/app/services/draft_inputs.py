"""Read a draft's adjustments and disclosure answers onto the statutory inputs.

An adjustment is a balanced draft journal. It is not a second source document.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.services.reconciliation import statutory_lines
from findraft.engine.money import money
from findraft.engine.schemas import TBLine
from findraft.models.adjustments import (
    AdjustmentJournal,
    AdjustmentLine,
    DisclosureAnswer,
)
from findraft.models.draft_version import DraftVersion


class DraftInputError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class AdjustedInputs:
    tb_lines: list[TBLine]
    mappings: dict[str, str]
    flags: dict[str, bool]
    adjustment_keys: frozenset[tuple[str, str, Decimal]]


async def latest_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    tb_version_id: uuid.UUID,
) -> DraftVersion | None:
    await aset_rls_org_id(session, org_id)
    return (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == org_id,
                DraftVersion.tb_version_id == tb_version_id,
            )
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
    ).first()


def snapshot_dict(draft: DraftVersion) -> dict[str, object] | None:
    if draft.status != "final" or draft.snapshot is None:
        return None
    return draft.snapshot


async def _lines_for_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> list[AdjustmentLine]:
    await aset_rls_org_id(session, org_id)
    journals = (
        await session.scalars(
            select(AdjustmentJournal)
            .where(
                AdjustmentJournal.org_id == org_id,
                AdjustmentJournal.draft_version_id == draft_id,
            )
            .order_by(AdjustmentJournal.created_at, AdjustmentJournal.id)
        )
    ).all()
    if not journals:
        return []
    journal_ids = [journal.id for journal in journals]
    return list(
        (
            await session.scalars(
                select(AdjustmentLine)
                .where(
                    AdjustmentLine.org_id == org_id,
                    AdjustmentLine.journal_id.in_(journal_ids),
                )
                .order_by(AdjustmentLine.journal_id, AdjustmentLine.line_no)
            )
        ).all()
    )


async def disclosure_flags(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> dict[str, bool]:
    await aset_rls_org_id(session, org_id)
    rows = (
        await session.scalars(
            select(DisclosureAnswer).where(
                DisclosureAnswer.org_id == org_id,
                DisclosureAnswer.draft_version_id == draft_id,
            )
        )
    ).all()
    return {row.flag_name: row.answer for row in rows}


def apply_adjustment_lines(
    tb_lines: list[TBLine],
    mappings: dict[str, str],
    lines: list[AdjustmentLine],
) -> AdjustedInputs:
    """Append adjustment lines. A code already mapped elsewhere is refused."""
    allowed = statutory_lines()
    combined = list(tb_lines)
    mapped = dict(mappings)
    keys: set[tuple[str, str, Decimal]] = set()
    for line in lines:
        if line.canonical_line not in allowed:
            raise DraftInputError(
                f"adjustment line {line.canonical_line} is not a statutory line"
            )
        existing = mapped.get(line.nominal_code)
        if existing is not None and existing != line.canonical_line:
            raise DraftInputError(
                f"account {line.nominal_code} is already mapped to {existing}"
            )
        mapped[line.nominal_code] = line.canonical_line
        balance = money(line.debit - line.credit)
        keys.add((line.nominal_code, line.account_name, balance))
        combined.append(
            TBLine(
                nominal_code=line.nominal_code,
                account_name=line.account_name,
                debit=line.debit,
                credit=line.credit,
            )
        )
    return AdjustedInputs(
        tb_lines=combined,
        mappings=mapped,
        flags={},
        adjustment_keys=frozenset(keys),
    )


async def adjusted_for_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    draft: DraftVersion,
    tb_lines: list[TBLine],
    mappings: dict[str, str],
) -> AdjustedInputs:
    lines = await _lines_for_draft(session, org_id=org_id, draft_id=draft.id)
    flags = await disclosure_flags(session, org_id=org_id, draft_id=draft.id)
    adjusted = apply_adjustment_lines(tb_lines, mappings, lines)
    return AdjustedInputs(
        tb_lines=adjusted.tb_lines,
        mappings=adjusted.mappings,
        flags=flags,
        adjustment_keys=adjusted.adjustment_keys,
    )
