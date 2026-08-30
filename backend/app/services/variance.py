"""Period-on-period variance analysis (Product Spec §4.3, §10.3, Appendix B).

Compares leaf statement line items from current vs prior SOPL+SOFP. Subtotals
are excluded — their variance is a consequence of component lines. All
arithmetic uses Decimal; division by a zero prior returns None for variance_pct.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Sequence

from app.schemas.variance import (
    VarianceAnalysisResult,
    VarianceDirection,
    VarianceItemRecord,
)


class StatementLineLike(Protocol):
    """Minimal statement line shape from statements.build_sopl / build_sofp."""

    line_item_code: str
    line_item_name: str
    amount: Decimal
    is_subtotal: bool


def is_material(
    variance_amount: Decimal,
    variance_pct: Decimal,
    threshold_abs: Decimal,
    threshold_pct: Decimal,
) -> bool:
    """Appendix B materiality rule — exact signature and body."""
    return abs(variance_amount) >= threshold_abs or abs(variance_pct) >= threshold_pct


def compute_variance(
    current_lines: Sequence[StatementLineLike],
    prior_lines: Sequence[StatementLineLike],
    *,
    materiality_threshold_pct: Decimal,
    materiality_threshold_abs: Decimal,
) -> VarianceAnalysisResult:
    """Compare leaf lines across periods; return §10.3 variance items (no commentary)."""
    current_by_code = _leaf_index(current_lines)
    prior_by_code = _leaf_index(prior_lines)

    ordered_codes = _ordered_union(current_by_code, prior_by_code)
    items: list[VarianceItemRecord] = []

    for code in ordered_codes:
        current = current_by_code.get(code)
        prior = prior_by_code.get(code)

        if current is not None and prior is not None:
            current_amount = current.amount
            prior_amount = prior.amount
            variance_amount = current_amount - prior_amount
            variance_pct = _variance_pct(variance_amount, prior_amount)
            if variance_amount > Decimal("0"):
                direction: VarianceDirection = "increase"
            elif variance_amount < Decimal("0"):
                direction = "decrease"
            else:
                # Unchanged amount — still report; treat as non-directional increase.
                direction = "increase"
            line_item_name = current.line_item_name
        elif current is not None:
            current_amount = current.amount
            prior_amount = Decimal("0.00")
            variance_amount = current_amount - prior_amount
            variance_pct = _variance_pct(variance_amount, prior_amount)
            direction = "new"
            line_item_name = current.line_item_name
        else:
            assert prior is not None
            current_amount = Decimal("0.00")
            prior_amount = prior.amount
            variance_amount = current_amount - prior_amount
            variance_pct = _variance_pct(variance_amount, prior_amount)
            direction = "removed"
            line_item_name = prior.line_item_name

        material = _is_material_for_item(
            variance_amount,
            variance_pct,
            materiality_threshold_abs,
            materiality_threshold_pct,
        )

        items.append(
            VarianceItemRecord(
                line_item_code=code,
                line_item_name=line_item_name,
                current_amount=_money_str(current_amount),
                prior_amount=_money_str(prior_amount),
                variance_amount=_money_str(variance_amount),
                variance_pct=_pct_str(variance_pct) if variance_pct is not None else None,
                direction=direction,
                is_material=material,
            )
        )

    return VarianceAnalysisResult(items=items)


def _leaf_index(
    lines: Sequence[StatementLineLike],
) -> dict[str, StatementLineLike]:
    """Index leaf lines by code. Last occurrence wins if duplicates appear."""
    indexed: dict[str, StatementLineLike] = {}
    for line in lines:
        if not line.is_subtotal:
            indexed[line.line_item_code] = line
    return indexed


def _ordered_union(
    current_by_code: dict[str, StatementLineLike],
    prior_by_code: dict[str, StatementLineLike],
) -> list[str]:
    """Current leaf order first, then prior-only (removed) codes in prior order."""
    codes: list[str] = []
    seen: set[str] = set()
    for code in current_by_code:
        codes.append(code)
        seen.add(code)
    for code in prior_by_code:
        if code not in seen:
            codes.append(code)
            seen.add(code)
    return codes


def _variance_pct(variance_amount: Decimal, prior_amount: Decimal) -> Decimal | None:
    """(variance / abs(prior)) * 100. None when prior is zero (Cursor Rules §6.3)."""
    if prior_amount == Decimal("0"):
        return None
    return (variance_amount / abs(prior_amount)) * Decimal("100")


def _is_material_for_item(
    variance_amount: Decimal,
    variance_pct: Decimal | None,
    threshold_abs: Decimal,
    threshold_pct: Decimal,
) -> bool:
    """Apply Appendix B is_material; when pct is None only the absolute threshold applies."""
    if variance_pct is None:
        return abs(variance_amount) >= threshold_abs
    return is_material(variance_amount, variance_pct, threshold_abs, threshold_pct)


def _money_str(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01'))}"


def _pct_str(pct: Decimal) -> str:
    return f"{pct.quantize(Decimal('0.01'))}"
