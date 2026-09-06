"""Copilot evidence-pack and grounded-answer schemas.

Amounts are always decimal *strings*. The evidence pack is the only numeric
source of truth for grounding — the model is never trusted to self-police.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CopilotIntent(StrEnum):
    """v1 question categories (deterministic classifier)."""

    PERIOD_SUMMARY = "period_summary"
    VARIANCE = "variance"
    EXPENSE_MIX = "expense_mix"
    TREND = "trend"
    MATERIAL_ITEMS = "material_items"
    RISK_HEALTH = "risk_health"
    GLOSSARY = "glossary"
    UNSUPPORTED = "unsupported"


class CopilotToolName(StrEnum):
    GET_PERFORMANCE_PERIOD = "get_performance_period"
    GET_VARIANCE = "get_variance"
    GET_EXPENSE_MIX = "get_expense_mix"
    GET_RISK_FLAGS = "get_risk_flags"
    GET_COMMENTARY = "get_commentary"
    GET_HEALTH = "get_health"
    GET_GLOSSARY = "get_glossary"


class EvidencePeriodMetrics(BaseModel):
    """KPI snapshot for one historical period."""

    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    period_end: date
    metrics: dict[str, str | None]  # code → Decimal string


class EvidenceExpenseShare(BaseModel):
    """One expense-mix slice for the selected period."""

    model_config = ConfigDict(extra="forbid")

    line_code: str
    label: str
    amount: str


class EvidenceVarianceItem(BaseModel):
    """One variance row (amounts as strings)."""

    model_config = ConfigDict(extra="forbid")

    line_code: str
    label: str
    current_amount: str
    prior_amount: str
    variance_amount: str
    variance_pct: str | None = None
    direction: str
    is_material: bool


class EvidenceRiskFlag(BaseModel):
    """One risk flag description (no invented numbers)."""

    model_config = ConfigDict(extra="forbid")

    rule_name: str
    severity: str
    description: str
    recommended_action: str | None = None
    affected_account_codes: list[str] = Field(default_factory=list)


class EvidenceCommentary(BaseModel):
    """Persisted variance commentary text for one line."""

    model_config = ConfigDict(extra="forbid")

    line_code: str
    text: str
    confidence: str | None = None


class EvidenceHealth(BaseModel):
    """Business Health text summary (no charts)."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    key_points: list[str] = Field(default_factory=list)
    confidence: str | None = None


class EvidenceGlossaryEntry(BaseModel):
    """Static definition — never an invented number."""

    model_config = ConfigDict(extra="forbid")

    term: str
    definition: str


class EvidencePack(BaseModel):
    """Structured evidence JSON injected into the Copilot prompt.

    No free-form TB dumps. All monetary values are strings.
    """

    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    company_name: str
    tb_id: uuid.UUID
    period_end: date
    prior_period_end: date | None = None
    currency: str
    intent: CopilotIntent
    tools_used: list[CopilotToolName] = Field(default_factory=list)
    periods: list[EvidencePeriodMetrics] = Field(default_factory=list)
    expense_mix: list[EvidenceExpenseShare] = Field(default_factory=list)
    variance_items: list[EvidenceVarianceItem] = Field(default_factory=list)
    risk_flags: list[EvidenceRiskFlag] = Field(default_factory=list)
    commentaries: list[EvidenceCommentary] = Field(default_factory=list)
    health: EvidenceHealth | None = None
    glossary: list[EvidenceGlossaryEntry] = Field(default_factory=list)
    refusal_reason: str | None = None

    def all_line_codes(self) -> set[str]:
        codes: set[str] = set()
        for period in self.periods:
            codes.update(k for k, v in period.metrics.items() if v is not None)
        codes.update(item.line_code for item in self.expense_mix)
        codes.update(item.line_code for item in self.variance_items)
        codes.update(item.line_code for item in self.commentaries)
        for flag in self.risk_flags:
            codes.update(flag.affected_account_codes)
        return codes

    def all_amount_strings(self) -> set[str]:
        """Normalized amount tokens present in this pack (no currency symbols)."""
        amounts: set[str] = set()
        for period in self.periods:
            for value in period.metrics.values():
                if value is not None:
                    amounts.add(normalize_numeric_token(value))
        for item in self.expense_mix:
            amounts.add(normalize_numeric_token(item.amount))
        for item in self.variance_items:
            amounts.add(normalize_numeric_token(item.current_amount))
            amounts.add(normalize_numeric_token(item.prior_amount))
            amounts.add(normalize_numeric_token(item.variance_amount))
            if item.variance_pct is not None:
                amounts.add(normalize_numeric_token(item.variance_pct))
        return {a for a in amounts if a}


class CopilotCitation(BaseModel):
    """One citation chip in a grounded answer."""

    model_config = ConfigDict(extra="forbid")

    source: Literal[
        "performance",
        "variance",
        "expense_mix",
        "risk",
        "commentary",
        "health",
        "glossary",
    ]
    line_code: str | None = None
    period_end: date | None = None


class CopilotAnswer(BaseModel):
    """LLM (or refusal) payload before/after grounding."""

    model_config = ConfigDict(extra="forbid")

    answer_markdown: str
    citations: list[CopilotCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    refused: bool = False
    refusal_message: str | None = None


class GroundedCopilotAnswer(BaseModel):
    """Post-grounding answer ready for the UI."""

    model_config = ConfigDict(extra="forbid")

    answer_markdown: str
    citations: list[CopilotCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    refused: bool = False
    refusal_message: str | None = None
    dropped_sentence_count: int = 0


REFUSAL_MESSAGE = "I don't have that in the evidence for this period."


def normalize_numeric_token(raw: str) -> str:
    """Strip currency symbols / commas / whitespace / %; keep digits, sign, dot."""
    cleaned = (
        raw.strip()
        .replace(",", "")
        .replace("£", "")
        .replace("€", "")
        .replace("$", "")
        .replace("%", "")
        .replace(" ", "")
    )
    if cleaned.endswith("."):
        cleaned = cleaned[:-1]
    return cleaned


class CopilotAskRequest(BaseModel):
    """POST /trial-balances/{tb_id}/copilot body."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)


class CopilotAskResponse(BaseModel):
    """Grounded Copilot answer plus context for the slide-over chip."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    period_end: date
    prior_period_end: date | None = None
    answer_markdown: str
    citations: list[CopilotCitation] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    refused: bool = False
    refusal_message: str | None = None
    dropped_sentence_count: int = 0
    turn_id: uuid.UUID
