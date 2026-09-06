"""Deterministic Copilot intent classification and tool selection (v1)."""

from __future__ import annotations

import re

from app.schemas.copilot import CopilotIntent, CopilotToolName

# More specific patterns first.
_INTENT_PATTERNS: tuple[tuple[CopilotIntent, re.Pattern[str]], ...] = (
    (
        CopilotIntent.UNSUPPORTED,
        re.compile(
            r"\b("
            r"forecast|predict|next year|next quarter|projection|"
            r"tax advice|corporation tax|vat return|"
            r"should we cut|what should we cut|reduce headcount|"
            r"journal entr|posting|double[- ]entry|"
            r"invest in|buy shares|valuation"
            r")\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.GLOSSARY,
        re.compile(
            r"\b(what (does|is)|define|definition|meaning of|explain the term)\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.EXPENSE_MIX,
        re.compile(
            r"\b(expense mix|cost mix|cost breakdown|where (is|does) .*spend|"
            r"operating expenses? breakdown|cost of sales share)\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.TREND,
        re.compile(
            r"\b(trend|over time|last \d+ periods?|how has|moved over|"
            r"trajectory|multi[- ]period)\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.MATERIAL_ITEMS,
        re.compile(
            r"\b(material (items?|variances?|movements?)|biggest movements?|"
            r"largest variances?)\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.RISK_HEALTH,
        re.compile(
            r"\b(risk flags?|risks?\b|business health|health summary|"
            r"executive summary)\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.VARIANCE,
        re.compile(
            r"\b(variance|what moved|vs prior|versus prior|compared to prior|"
            r"period[- ]on[- ]period|why did .* change)\b",
            re.I,
        ),
    ),
    (
        CopilotIntent.PERIOD_SUMMARY,
        re.compile(
            r"\b(summar(y|ise|ize)|overview|how did .+ (do|perform)|"
            r"period summary|this period)\b",
            re.I,
        ),
    ),
)

_TOOLS_BY_INTENT: dict[CopilotIntent, tuple[CopilotToolName, ...]] = {
    CopilotIntent.PERIOD_SUMMARY: (
        CopilotToolName.GET_PERFORMANCE_PERIOD,
        CopilotToolName.GET_COMMENTARY,
        CopilotToolName.GET_HEALTH,
    ),
    CopilotIntent.VARIANCE: (
        CopilotToolName.GET_VARIANCE,
        CopilotToolName.GET_COMMENTARY,
    ),
    CopilotIntent.EXPENSE_MIX: (
        CopilotToolName.GET_EXPENSE_MIX,
        CopilotToolName.GET_PERFORMANCE_PERIOD,
    ),
    CopilotIntent.TREND: (CopilotToolName.GET_PERFORMANCE_PERIOD,),
    CopilotIntent.MATERIAL_ITEMS: (
        CopilotToolName.GET_VARIANCE,
        CopilotToolName.GET_COMMENTARY,
    ),
    CopilotIntent.RISK_HEALTH: (
        CopilotToolName.GET_RISK_FLAGS,
        CopilotToolName.GET_HEALTH,
    ),
    CopilotIntent.GLOSSARY: (CopilotToolName.GET_GLOSSARY,),
    CopilotIntent.UNSUPPORTED: (),
}


def classify_intent(question: str) -> CopilotIntent:
    """Return the best-matching v1 intent for ``question``."""
    text = question.strip()
    if not text:
        return CopilotIntent.UNSUPPORTED
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(text):
            return intent
    if re.search(r"\b(revenue|profit|cash|expense|margin|period)\b", text, re.I):
        return CopilotIntent.PERIOD_SUMMARY
    return CopilotIntent.UNSUPPORTED


def tools_for_intent(intent: CopilotIntent) -> tuple[CopilotToolName, ...]:
    """Tools required to build an evidence pack for ``intent``."""
    return _TOOLS_BY_INTENT[intent]
