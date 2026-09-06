"""Comparative (current + prior) statement face merge.

Builds side-by-side period columns for SOPL / SOFP / SOCIE by joining
nil-filtered face lines on ``line_item_code``. Each side is filtered
independently first, so SOFP NC/current section visibility and SOCIE
rollforwards stay period-faithful (S1 design).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from app.services.statements import LINE_ITEM_NAMES, STATEMENT_FACE_ORDER


class FaceLineLike(Protocol):
    id: uuid.UUID
    line_item_code: str
    line_item_name: str
    amount: Decimal | str
    is_subtotal: bool
    source_account_ids: Sequence[uuid.UUID] | None


@dataclass(frozen=True, slots=True)
class ComparativeFaceLine:
    """One comparative face row. ``None`` amount → em dash on that side."""

    id: uuid.UUID
    line_item_code: str
    line_item_name: str
    amount: str | None
    prior_amount: str | None
    is_subtotal: bool
    display_order: int
    source_account_ids: list[uuid.UUID]


def _money_str(amount: Decimal | str) -> str:
    if isinstance(amount, str):
        return amount
    return f"{amount.quantize(Decimal('0.01'))}"


def merge_comparative_face_lines(
    statement_type: str,
    current_lines: Sequence[FaceLineLike],
    prior_lines: Sequence[FaceLineLike],
) -> list[ComparativeFaceLine]:
    """Union current + prior face rows in canonical statement order.

    A line appears when it survives nil-filtering on either side.
    Missing side → ``None`` (UI renders an em dash).
    """
    order = STATEMENT_FACE_ORDER.get(statement_type)
    if order is None:
        raise ValueError(f"Unknown statement_type for comparative merge: {statement_type!r}")

    current_by_code = {line.line_item_code: line for line in current_lines}
    prior_by_code = {line.line_item_code: line for line in prior_lines}

    # Preserve any unexpected codes after the canonical block (defensive).
    extra_codes = [
        code
        for code in list(current_by_code) + list(prior_by_code)
        if code not in order
    ]
    # Dedupe extras while preserving first-seen order.
    seen_extra: set[str] = set()
    extras: list[str] = []
    for code in extra_codes:
        if code in seen_extra:
            continue
        seen_extra.add(code)
        extras.append(code)

    merged: list[ComparativeFaceLine] = []
    display_order = 1
    for code in (*order, *extras):
        current = current_by_code.get(code)
        prior = prior_by_code.get(code)
        if current is None and prior is None:
            continue

        primary = current if current is not None else prior
        assert primary is not None
        if current is not None:
            name = current.line_item_name
        elif prior is not None:
            name = prior.line_item_name
        else:
            name = LINE_ITEM_NAMES.get(code, code)
        merged.append(
            ComparativeFaceLine(
                id=primary.id,
                line_item_code=code,
                line_item_name=name,
                amount=_money_str(current.amount) if current is not None else None,
                prior_amount=_money_str(prior.amount) if prior is not None else None,
                is_subtotal=bool(primary.is_subtotal),
                display_order=display_order,
                source_account_ids=list(primary.source_account_ids or []),
            )
        )
        display_order += 1
    return merged
