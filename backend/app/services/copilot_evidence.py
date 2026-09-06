"""Build Copilot evidence packs from already-loaded statement artifacts.

Routers fetch owned TB data under RLS; this module assembles the structured
JSON evidence pack (amounts as strings only). No free-form TB dumps.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from app.schemas.commentary import BusinessHealthResult, CommentaryRecord
from app.schemas.copilot import (
    REFUSAL_MESSAGE,
    CopilotIntent,
    CopilotToolName,
    EvidenceCommentary,
    EvidenceExpenseShare,
    EvidenceHealth,
    EvidencePack,
    EvidencePeriodMetrics,
    EvidenceRiskFlag,
    EvidenceVarianceItem,
)
from app.schemas.risk import RiskFlagRecord
from app.schemas.variance import VarianceItemRecord
from app.services.copilot_glossary import lookup_glossary
from app.services.copilot_intent import classify_intent, tools_for_intent
from app.services.performance import EXPENSE_CODES, PeriodMetrics, expense_share_amounts

_EXPENSE_LABELS: dict[str, str] = {
    "cost_of_sales": "Cost of sales",
    "operating_expenses": "Operating expenses",
    "depreciation": "Depreciation",
}


def _money_str(value: Decimal | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def period_metrics_to_evidence(
    periods: Sequence[PeriodMetrics],
) -> list[EvidencePeriodMetrics]:
    """Serialize performance PeriodMetrics → evidence rows (string amounts)."""
    rows: list[EvidencePeriodMetrics] = []
    for period in periods:
        metrics = {code: _money_str(amount) for code, amount in period.metrics.items()}
        rows.append(
            EvidencePeriodMetrics(
                tb_id=period.tb_id,
                period_end=period.period_end,
                metrics=metrics,
            )
        )
    return rows


def expense_mix_to_evidence(
    metrics: Mapping[str, Decimal | None],
) -> list[EvidenceExpenseShare]:
    """Build expense-mix evidence from current-period metrics."""
    shares = expense_share_amounts(dict(metrics))
    return [
        EvidenceExpenseShare(
            line_code=code,
            label=_EXPENSE_LABELS.get(code, code),
            amount=_money_str(amount) or "0.00",
        )
        for code, amount in shares.items()
        if code in EXPENSE_CODES
    ]


def variance_items_to_evidence(
    items: Sequence[VarianceItemRecord],
    *,
    material_only: bool = False,
) -> list[EvidenceVarianceItem]:
    """Map variance schema rows into evidence items."""
    rows: list[EvidenceVarianceItem] = []
    for item in items:
        if material_only and not item.is_material:
            continue
        rows.append(
            EvidenceVarianceItem(
                line_code=item.line_item_code,
                label=item.line_item_name,
                current_amount=item.current_amount,
                prior_amount=item.prior_amount,
                variance_amount=item.variance_amount,
                variance_pct=item.variance_pct,
                direction=item.direction,
                is_material=item.is_material,
            )
        )
    return rows


def risk_flags_to_evidence(flags: Sequence[RiskFlagRecord]) -> list[EvidenceRiskFlag]:
    """Map risk flag records into evidence rows."""
    rows: list[EvidenceRiskFlag] = []
    for flag in flags:
        affected = [acct.account_code for acct in (flag.affected_accounts or [])]
        rows.append(
            EvidenceRiskFlag(
                rule_name=flag.rule_name,
                severity=flag.severity,
                description=flag.description,
                recommended_action=flag.recommended_action,
                affected_account_codes=affected,
            )
        )
    return rows


def commentary_to_evidence(
    commentaries: Mapping[str, CommentaryRecord],
) -> list[EvidenceCommentary]:
    """Flatten per-line commentary map into evidence rows."""
    return [
        EvidenceCommentary(
            line_code=code,
            text=record.text,
            confidence=record.confidence,
        )
        for code, record in commentaries.items()
        if record.text.strip()
    ]


def health_to_evidence(health: BusinessHealthResult | None) -> EvidenceHealth | None:
    """Include Business Health text when non-empty."""
    if health is None:
        return None
    summary = health.summary.strip()
    points = [p.strip() for p in health.key_points if p.strip()]
    if not summary and not points:
        return None
    return EvidenceHealth(
        summary=summary,
        key_points=points,
        confidence=health.confidence,
    )


def build_evidence_pack(
    *,
    question: str,
    company_id: uuid.UUID,
    company_name: str,
    tb_id: uuid.UUID,
    period_end: date,
    currency: str,
    prior_period_end: date | None = None,
    periods: Sequence[PeriodMetrics] | None = None,
    variance_items: Sequence[VarianceItemRecord] | None = None,
    risk_flags: Sequence[RiskFlagRecord] | None = None,
    commentaries: Mapping[str, CommentaryRecord] | None = None,
    health: BusinessHealthResult | None = None,
) -> EvidencePack:
    """Assemble an evidence pack for ``question`` from pre-fetched tool data."""
    intent = classify_intent(question)
    tools = list(tools_for_intent(intent))

    if intent == CopilotIntent.UNSUPPORTED:
        return EvidencePack(
            company_id=company_id,
            company_name=company_name,
            tb_id=tb_id,
            period_end=period_end,
            prior_period_end=prior_period_end,
            currency=currency,
            intent=intent,
            tools_used=[],
            refusal_reason=REFUSAL_MESSAGE,
        )

    pack = EvidencePack(
        company_id=company_id,
        company_name=company_name,
        tb_id=tb_id,
        period_end=period_end,
        prior_period_end=prior_period_end,
        currency=currency,
        intent=intent,
        tools_used=tools,
    )

    if CopilotToolName.GET_PERFORMANCE_PERIOD in tools and periods:
        pack.periods = period_metrics_to_evidence(periods)

    if CopilotToolName.GET_EXPENSE_MIX in tools and periods:
        current = next((p for p in periods if p.tb_id == tb_id), periods[-1])
        pack.expense_mix = expense_mix_to_evidence(current.metrics)
        if not pack.periods:
            pack.periods = period_metrics_to_evidence([current])

    if CopilotToolName.GET_VARIANCE in tools and variance_items is not None:
        material_only = intent == CopilotIntent.MATERIAL_ITEMS
        pack.variance_items = variance_items_to_evidence(
            variance_items, material_only=material_only
        )

    if CopilotToolName.GET_RISK_FLAGS in tools and risk_flags is not None:
        pack.risk_flags = risk_flags_to_evidence(risk_flags)

    if CopilotToolName.GET_COMMENTARY in tools and commentaries is not None:
        pack.commentaries = commentary_to_evidence(commentaries)

    if CopilotToolName.GET_HEALTH in tools:
        pack.health = health_to_evidence(health)

    if CopilotToolName.GET_GLOSSARY in tools:
        pack.glossary = lookup_glossary(question)
        if not pack.glossary:
            pack.refusal_reason = REFUSAL_MESSAGE

    if intent != CopilotIntent.GLOSSARY and not _pack_has_usable_evidence(pack):
        pack.refusal_reason = REFUSAL_MESSAGE

    return pack


def _pack_has_usable_evidence(pack: EvidencePack) -> bool:
    if pack.periods and any(
        any(v is not None for v in period.metrics.values()) for period in pack.periods
    ):
        return True
    if pack.expense_mix or pack.variance_items or pack.risk_flags:
        return True
    if pack.commentaries or pack.health is not None or pack.glossary:
        return True
    return False
