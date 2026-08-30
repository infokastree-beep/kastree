"""AI commentary — material variances and business health (Product Spec §4.3).

Uses GPT-4o only (temperature 0.2). Section 7.1 reserves GPT-4o-mini for the
mapping tie-breaker and risk explanations — commentary has no alternate-model
fallback. Retry budget matches mapper Tier 4 timing (1 initial + 3 retries,
backoff 1s/2s/4s) but stays on gpt-4o. On total failure returns empty results —
never raises (statements still generate).
"""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from typing import Any, Callable, Protocol, Sequence

from openai import OpenAI

from app.schemas.commentary import (
    BusinessHealthResult,
    CommentaryRecord,
    VarianceCommentaryResult,
)
from app.schemas.variance import VarianceAnalysisResult, VarianceItemRecord
from app.services.llm import BUSINESS_HEALTH_SYSTEM, VARIANCE_COMMENTARY_SYSTEM

logger = logging.getLogger(__name__)

# Commentary is GPT-4o only (Section 7.1). No GPT-4o-mini fallback — that model
# is reserved for mapping tie-breaker and risk explanations.
COMMENTARY_MODEL = "gpt-4o"
COMMENTARY_TEMPERATURE = 0.2
# 1 initial + 3 retries, backoff 1s/2s/4s (same timing as mapper Tier 4).
LLM_MAX_ATTEMPTS = 4
LLM_BACKOFF_SECONDS = (1, 2, 4)

# Relative change within this band is treated as "stable" when deriving trends.
_STABLE_PCT_BAND = Decimal("5")

SleepFn = Callable[[float], None]

_VALID_CONFIDENCE: frozenset[str] = frozenset({"high", "medium", "low"})

_DIRECTION_VERBS: dict[str, str] = {
    "increase": "increased",
    "decrease": "decreased",
    "new": "is new",
    "removed": "has been removed",
}


class StatementLineLike(Protocol):
    line_item_code: str
    amount: Decimal
    is_subtotal: bool


def generate_variance_commentary(
    variance_result: VarianceAnalysisResult,
    *,
    openai_client: OpenAI | None = None,
    sleep: SleepFn = time.sleep,
) -> VarianceCommentaryResult:
    """Draft commentary for material variance items only. Empty on LLM failure."""
    material_items = [item for item in variance_result.items if item.is_material]
    if not material_items:
        return VarianceCommentaryResult(commentaries={})

    user_prompt = _build_variance_commentary_user_prompt(material_items)
    client = openai_client if openai_client is not None else OpenAI()

    try:
        payload = _complete_commentary_json(
            client,
            system_prompt=VARIANCE_COMMENTARY_SYSTEM,
            user_prompt=user_prompt,
            sleep=sleep,
        )
    except Exception as exc:
        logger.error(
            "Variance commentary unavailable after 4 gpt-4o attempts: %s",
            exc,
        )
        return VarianceCommentaryResult(commentaries={})

    return _parse_variance_commentaries(material_items, payload)


def generate_business_health_summary(
    current_sopl: Sequence[StatementLineLike],
    prior_sopl: Sequence[StatementLineLike],
    current_sofp: Sequence[StatementLineLike],
    prior_sofp: Sequence[StatementLineLike],
    *,
    openai_client: OpenAI | None = None,
    sleep: SleepFn = time.sleep,
) -> BusinessHealthResult:
    """Draft business-health summary from directional trends only. Empty on failure."""
    user_prompt = _build_business_health_user_prompt(
        current_sopl, prior_sopl, current_sofp, prior_sofp
    )
    client = openai_client if openai_client is not None else OpenAI()

    try:
        payload = _complete_commentary_json(
            client,
            system_prompt=BUSINESS_HEALTH_SYSTEM,
            user_prompt=user_prompt,
            sleep=sleep,
        )
    except Exception as exc:
        logger.error(
            "Business health summary unavailable after 4 gpt-4o attempts: %s",
            exc,
        )
        return _empty_business_health()

    return _parse_business_health(payload)


def _build_variance_commentary_user_prompt(
    material_items: Sequence[VarianceItemRecord],
) -> str:
    """Build the user prompt from name/direction/pct only.

    Deliberate omission: VarianceItemRecord also carries current_amount,
    prior_amount, and variance_amount. Those monetary fields must NEVER be sent
    to the LLM (.cursorrules §7.1 / Product Spec §4.3 — no raw numbers in prompts).
    Only line_item_name, direction, and variance_pct are included below.
    """
    lines: list[str] = []
    for index, item in enumerate(material_items, start=1):
        # Do not reference item.current_amount, item.prior_amount, or
        # item.variance_amount — even though they exist on the record.
        verb = _DIRECTION_VERBS.get(item.direction, item.direction)
        if item.direction in ("new", "removed"):
            lines.append(f"{index}. {item.line_item_name} {verb} compared to prior period")
        elif item.variance_pct is None:
            lines.append(
                f"{index}. {item.line_item_name} has {verb} compared to prior period"
            )
        else:
            lines.append(
                f"{index}. {item.line_item_name} has {verb} by approximately "
                f"{item.variance_pct}%"
            )
    return (
        "Draft commentary for the following movements compared to prior period:\n"
        + "\n".join(lines)
    )


def _build_business_health_user_prompt(
    current_sopl: Sequence[StatementLineLike],
    prior_sopl: Sequence[StatementLineLike],
    current_sofp: Sequence[StatementLineLike],
    prior_sofp: Sequence[StatementLineLike],
) -> str:
    """Derive directional trends in Python; never pass Decimals into the prompt."""
    current_sopl_map = _amount_map(current_sopl)
    prior_sopl_map = _amount_map(prior_sopl)
    current_sofp_map = _amount_map(current_sofp)
    prior_sofp_map = _amount_map(prior_sofp)

    gross_margin_trend = _gross_margin_trend(current_sopl_map, prior_sopl_map)
    opex_vs_revenue = _operating_expense_vs_revenue(current_sopl_map, prior_sopl_map)
    cash_position = _directional_trend(
        current_sofp_map.get("cash"),
        prior_sofp_map.get("cash"),
    )
    debt_levels = _directional_trend(
        current_sofp_map.get("loans"),
        prior_sofp_map.get("loans"),
    )

    return (
        f"Gross margin trend: {gross_margin_trend}. "
        f"Operating expense growth: {opex_vs_revenue}. "
        f"Cash position: {cash_position}. "
        f"Debt levels: {debt_levels}."
    )


def _amount_map(lines: Sequence[StatementLineLike]) -> dict[str, Decimal]:
    return {line.line_item_code: line.amount for line in lines if not line.is_subtotal}


def _gross_margin_trend(
    current: dict[str, Decimal],
    prior: dict[str, Decimal],
) -> str:
    current_gm = _gross_margin_pct(current)
    prior_gm = _gross_margin_pct(prior)
    if current_gm is None or prior_gm is None:
        return "unavailable"
    delta = current_gm - prior_gm
    if abs(delta) < _STABLE_PCT_BAND:
        return "stable"
    return "improving" if delta > 0 else "declining"


def _gross_margin_pct(amounts: dict[str, Decimal]) -> Decimal | None:
    revenue = amounts.get("revenue")
    cost_of_sales = amounts.get("cost_of_sales", Decimal("0"))
    if revenue is None or revenue == Decimal("0"):
        return None
    return ((revenue - cost_of_sales) / abs(revenue)) * Decimal("100")


def _operating_expense_vs_revenue(
    current: dict[str, Decimal],
    prior: dict[str, Decimal],
) -> str:
    rev_growth = _growth_pct(current.get("revenue"), prior.get("revenue"))
    opex_growth = _growth_pct(
        current.get("operating_expenses"),
        prior.get("operating_expenses"),
    )
    if rev_growth is None or opex_growth is None:
        return "unavailable"
    diff = opex_growth - rev_growth
    if abs(diff) < _STABLE_PCT_BAND:
        return "in line with revenue"
    if diff > 0:
        return "faster than revenue"
    return "slower than revenue"


def _growth_pct(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    if current is None or prior is None:
        return None
    if prior == Decimal("0"):
        return None
    return ((current - prior) / abs(prior)) * Decimal("100")


def _directional_trend(current: Decimal | None, prior: Decimal | None) -> str:
    if current is None or prior is None:
        return "unavailable"
    if prior == Decimal("0"):
        if current == Decimal("0"):
            return "stable"
        return "improving" if current > 0 else "declining"
    change_pct = ((current - prior) / abs(prior)) * Decimal("100")
    if abs(change_pct) < _STABLE_PCT_BAND:
        return "stable"
    return "improving" if change_pct > 0 else "declining"


def _complete_commentary_json(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
    sleep: SleepFn,
) -> dict[str, Any]:
    """Four attempts on gpt-4o only (1 initial + 3 retries, backoff 1s/2s/4s).

    No model fallback: Section 7.1 assigns commentary to GPT-4o and reserves
    GPT-4o-mini for mapping / risk explanations.
    """
    last_error: Exception | None = None
    for attempt in range(LLM_MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=COMMENTARY_MODEL,
                temperature=COMMENTARY_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty LLM response content")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("LLM response is not a JSON object")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < LLM_MAX_ATTEMPTS - 1:
                sleep(LLM_BACKOFF_SECONDS[attempt])
    assert last_error is not None
    raise last_error


def _parse_variance_commentaries(
    material_items: Sequence[VarianceItemRecord],
    payload: dict[str, Any],
) -> VarianceCommentaryResult:
    raw_list = payload.get("commentaries")
    if not isinstance(raw_list, list):
        return VarianceCommentaryResult(commentaries={})

    by_line_name: dict[str, dict[str, Any]] = {}
    for entry in raw_list:
        if not isinstance(entry, dict):
            continue
        line_item = entry.get("line_item")
        if isinstance(line_item, str):
            by_line_name[line_item.strip().lower()] = entry

    commentaries: dict[str, CommentaryRecord] = {}
    for item in material_items:
        entry = by_line_name.get(item.line_item_code.lower()) or by_line_name.get(
            item.line_item_name.strip().lower()
        )
        if entry is None:
            continue
        text = entry.get("commentary")
        reasoning = entry.get("reasoning")
        confidence = entry.get("confidence")
        if not isinstance(text, str) or not isinstance(reasoning, str):
            continue
        if not isinstance(confidence, str) or confidence not in _VALID_CONFIDENCE:
            continue
        commentaries[item.line_item_code] = CommentaryRecord(
            text=text,
            is_ai_generated=True,
            is_edited=False,
            reasoning=reasoning,
            confidence=confidence,  # type: ignore[arg-type]
        )
    return VarianceCommentaryResult(commentaries=commentaries)


def _parse_business_health(payload: dict[str, Any]) -> BusinessHealthResult:
    summary = payload.get("summary")
    key_points = payload.get("key_points")
    confidence = payload.get("confidence")
    if not isinstance(summary, str):
        return _empty_business_health()
    if not isinstance(key_points, list) or not all(
        isinstance(point, str) for point in key_points
    ):
        return _empty_business_health()
    if not isinstance(confidence, str) or confidence not in _VALID_CONFIDENCE:
        return _empty_business_health()

    reasoning = payload.get("reasoning")
    reasoning_str = reasoning if isinstance(reasoning, str) else None

    return BusinessHealthResult(
        summary=summary,
        key_points=list(key_points),
        confidence=confidence,  # type: ignore[arg-type]
        is_ai_generated=True,
        is_edited=False,
        reasoning=reasoning_str,
    )


def _empty_business_health() -> BusinessHealthResult:
    return BusinessHealthResult(
        summary="",
        key_points=[],
        confidence="low",
        is_ai_generated=False,
        is_edited=False,
        reasoning=None,
    )
