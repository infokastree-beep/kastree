"""Unit tests for Copilot intent classification and tool selection."""

from __future__ import annotations

import pytest

from app.schemas.copilot import CopilotIntent, CopilotToolName
from app.services.copilot_intent import classify_intent, tools_for_intent


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Summarise this period", CopilotIntent.PERIOD_SUMMARY),
        ("How did we perform this period?", CopilotIntent.PERIOD_SUMMARY),
        ("What moved vs prior?", CopilotIntent.VARIANCE),
        ("Why did revenue change?", CopilotIntent.VARIANCE),
        ("Show the expense mix", CopilotIntent.EXPENSE_MIX),
        ("How has revenue moved over 6 periods?", CopilotIntent.TREND),
        ("What are the material variances?", CopilotIntent.MATERIAL_ITEMS),
        ("What risk flags are open?", CopilotIntent.RISK_HEALTH),
        ("Business health summary please", CopilotIntent.RISK_HEALTH),
        ("What does gross profit mean?", CopilotIntent.GLOSSARY),
        ("Define material variance", CopilotIntent.GLOSSARY),
        ("Forecast next year's revenue", CopilotIntent.UNSUPPORTED),
        ("What should we cut?", CopilotIntent.UNSUPPORTED),
        ("Give me tax advice on VAT", CopilotIntent.UNSUPPORTED),
        ("Draft a journal entry for depreciation", CopilotIntent.UNSUPPORTED),
        ("", CopilotIntent.UNSUPPORTED),
        ("Tell me about revenue", CopilotIntent.PERIOD_SUMMARY),
    ],
)
def test_classify_intent(question: str, expected: CopilotIntent) -> None:
    assert classify_intent(question) == expected


def test_unsupported_beats_period_keywords() -> None:
    assert classify_intent("Forecast revenue for this period") == CopilotIntent.UNSUPPORTED


def test_tools_for_variance_include_commentary() -> None:
    tools = tools_for_intent(CopilotIntent.VARIANCE)
    assert CopilotToolName.GET_VARIANCE in tools
    assert CopilotToolName.GET_COMMENTARY in tools


def test_tools_for_unsupported_are_empty() -> None:
    assert tools_for_intent(CopilotIntent.UNSUPPORTED) == ()
