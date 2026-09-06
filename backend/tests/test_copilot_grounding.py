"""Unit tests for Copilot answer grounding — the safety-critical layer."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from app.schemas.copilot import (
    REFUSAL_MESSAGE,
    CopilotAnswer,
    CopilotCitation,
    CopilotIntent,
    EvidencePack,
    EvidencePeriodMetrics,
    EvidenceVarianceItem,
)
from app.services.copilot_grounding import ground_answer


def _pack_with_revenue_variance() -> EvidencePack:
    company_id = uuid4()
    tb_id = uuid4()
    return EvidencePack(
        company_id=company_id,
        company_name="Acme Ltd",
        tb_id=tb_id,
        period_end=date(2026, 9, 30),
        prior_period_end=date(2026, 8, 31),
        currency="EUR",
        intent=CopilotIntent.VARIANCE,
        periods=[
            EvidencePeriodMetrics(
                tb_id=tb_id,
                period_end=date(2026, 9, 30),
                metrics={"revenue": "120000.00", "cash": "25000.00"},
            )
        ],
        variance_items=[
            EvidenceVarianceItem(
                line_code="revenue",
                label="Revenue",
                current_amount="120000.00",
                prior_amount="100000.00",
                variance_amount="20000.00",
                variance_pct="20.00",
                direction="increase",
                is_material=True,
            )
        ],
    )


def test_keeps_grounded_sentence_and_drops_invented_figure() -> None:
    pack = _pack_with_revenue_variance()
    answer = CopilotAnswer(
        answer_markdown=(
            "Revenue increased by 20000.00 (20.00%). "
            "Marketing spent 999999.00 on campaigns. "
            "Cash remains at 25000.00."
        ),
        citations=[
            CopilotCitation(source="variance", line_code="revenue"),
            CopilotCitation(source="performance", line_code="cash"),
            CopilotCitation(source="variance", line_code="invented_line"),
        ],
        confidence="high",
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is False
    assert "20000.00" in grounded.answer_markdown
    assert "20.00" in grounded.answer_markdown
    assert "25000.00" in grounded.answer_markdown
    assert "999999.00" not in grounded.answer_markdown
    assert grounded.dropped_sentence_count == 1
    assert {c.line_code for c in grounded.citations} == {"revenue", "cash"}


def test_thousand_grouped_and_currency_tokens_match_pack() -> None:
    pack = _pack_with_revenue_variance()
    answer = CopilotAnswer(
        answer_markdown="Revenue is €120,000.00, up 20.00%.",
        citations=[CopilotCitation(source="variance", line_code="revenue")],
        confidence="medium",
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is False
    assert "120,000.00" in grounded.answer_markdown or "120000" in grounded.answer_markdown.replace(",", "")
    assert grounded.dropped_sentence_count == 0


def test_does_not_split_plain_decimal_into_fragments() -> None:
    """Regression: 20000.00 must not be tokenised as 200 + 00.00."""
    pack = _pack_with_revenue_variance()
    answer = CopilotAnswer(
        answer_markdown="Revenue increased by 20000.00 versus prior.",
        citations=[],
        confidence="high",
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is False
    assert grounded.dropped_sentence_count == 0
    assert "20000.00" in grounded.answer_markdown


def test_pure_narrative_without_numbers_is_kept() -> None:
    pack = _pack_with_revenue_variance()
    answer = CopilotAnswer(
        answer_markdown="Further investigation required on the revenue movement.",
        citations=[CopilotCitation(source="commentary", line_code="revenue")],
        confidence="low",
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is False
    assert grounded.dropped_sentence_count == 0
    assert grounded.citations[0].line_code == "revenue"


def test_all_ungrounded_sentences_become_refusal() -> None:
    pack = _pack_with_revenue_variance()
    answer = CopilotAnswer(
        answer_markdown="Profit jumped by 888888.00. Tax savings were 777.00.",
        citations=[CopilotCitation(source="variance", line_code="revenue")],
        confidence="high",
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is True
    assert grounded.refusal_message == REFUSAL_MESSAGE
    assert grounded.answer_markdown == ""
    assert grounded.citations == []
    assert grounded.dropped_sentence_count == 2


def test_pack_refusal_short_circuits() -> None:
    pack = EvidencePack(
        company_id=uuid4(),
        company_name="Acme Ltd",
        tb_id=uuid4(),
        period_end=date(2026, 9, 30),
        currency="EUR",
        intent=CopilotIntent.UNSUPPORTED,
        refusal_reason=REFUSAL_MESSAGE,
    )
    answer = CopilotAnswer(
        answer_markdown="Anything goes: 1.00",
        citations=[],
        confidence="high",
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is True
    assert grounded.refusal_message == REFUSAL_MESSAGE
    assert grounded.answer_markdown == ""


def test_model_refused_flag_preserved() -> None:
    pack = _pack_with_revenue_variance()
    answer = CopilotAnswer(
        answer_markdown="",
        refused=True,
        refusal_message=REFUSAL_MESSAGE,
    )
    grounded = ground_answer(answer, pack)
    assert grounded.refused is True
    assert grounded.refusal_message == REFUSAL_MESSAGE
