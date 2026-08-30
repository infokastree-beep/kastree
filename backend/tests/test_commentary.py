"""Tests for AI commentary service and commentary JSONB schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.commentary import (
    BusinessHealthResult,
    CommentaryRecord,
    VarianceCommentaryResult,
)
from app.schemas.variance import VarianceAnalysisResult, VarianceItemRecord
from app.services.commentary import (
    COMMENTARY_MODEL,
    COMMENTARY_TEMPERATURE,
    generate_business_health_summary,
    generate_variance_commentary,
)
from app.services.llm import BUSINESS_HEALTH_SYSTEM, VARIANCE_COMMENTARY_SYSTEM


@dataclass(frozen=True)
class _Line:
    line_item_code: str
    amount: Decimal
    is_subtotal: bool = False


def _line(code: str, amount: str, *, is_subtotal: bool = False) -> _Line:
    return _Line(code, Decimal(amount), is_subtotal)


def _variance_item(
    code: str,
    *,
    name: str,
    direction: str,
    variance_pct: str | None,
    is_material: bool,
    current_amount: str = "250000.00",
    prior_amount: str = "210000.00",
    variance_amount: str = "40000.00",
) -> VarianceItemRecord:
    return VarianceItemRecord(
        line_item_code=code,
        line_item_name=name,
        current_amount=current_amount,
        prior_amount=prior_amount,
        variance_amount=variance_amount,
        variance_pct=variance_pct,
        direction=direction,  # type: ignore[arg-type]
        is_material=is_material,
    )


def _mock_completion(payload: dict) -> MagicMock:
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _assert_prompt_has_no_money(user_content: str) -> None:
    for symbol in ("£", "€", "$"):
        assert symbol not in user_content
    # Absolute money strings that variance records carry must not leak into prompts.
    for forbidden in (
        "250000",
        "210000",
        "40000",
        "current_amount",
        "prior_amount",
        "variance_amount",
    ):
        assert forbidden not in user_content


# --- Schema -----------------------------------------------------------------


def test_commentary_record_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        CommentaryRecord.model_validate(
            {
                "text": "Revenue increased.",
                "is_ai_generated": True,
                "is_edited": False,
                "reasoning": "Material % move",
                "confidence": "high",
                "author": "gpt",
            }
        )

    errors = exc_info.value.errors()
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("author",)
        for error in errors
    )


def test_variance_commentary_result_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        VarianceCommentaryResult.model_validate(
            {"commentaries": {}, "banner": "unavailable"}
        )


def test_business_health_result_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        BusinessHealthResult.model_validate(
            {
                "summary": "ok",
                "key_points": ["a"],
                "confidence": "high",
                "score": 9,
            }
        )


# --- Material variance commentary -------------------------------------------


def test_variance_commentary_prompt_contains_no_monetary_figures() -> None:
    variance = VarianceAnalysisResult(
        items=[
            _variance_item(
                "revenue",
                name="Revenue",
                direction="increase",
                variance_pct="19.05",
                is_material=True,
                current_amount="250000.00",
                prior_amount="210000.00",
                variance_amount="40000.00",
            ),
            _variance_item(
                "cash",
                name="Cash",
                direction="increase",
                variance_pct="5.00",
                is_material=False,
                current_amount="10500.00",
                prior_amount="10000.00",
                variance_amount="500.00",
            ),
        ]
    )
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_completion(
        {
            "commentaries": [
                {
                    "line_item": "revenue",
                    "commentary": "Revenue rose versus the prior period.",
                    "reasoning": "Material increase above threshold.",
                    "confidence": "high",
                }
            ]
        }
    )

    result = generate_variance_commentary(
        variance,
        openai_client=client,
        sleep=lambda _: None,
    )

    assert set(result.commentaries) == {"revenue"}
    commentary = result.commentaries["revenue"]
    assert commentary.text == "Revenue rose versus the prior period."
    assert commentary.reasoning == "Material increase above threshold."
    assert commentary.confidence == "high"
    assert commentary.is_ai_generated is True
    assert commentary.is_edited is False

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == COMMENTARY_MODEL == "gpt-4o"
    assert call_kwargs["temperature"] == COMMENTARY_TEMPERATURE == 0.2
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["messages"][0] == {
        "role": "system",
        "content": VARIANCE_COMMENTARY_SYSTEM,
    }
    user_content = call_kwargs["messages"][1]["content"]
    assert "Revenue has increased by approximately 19.05%" in user_content
    assert "Cash" not in user_content  # non-material excluded
    _assert_prompt_has_no_money(user_content)
    assert "10500" not in user_content
    assert "10000" not in user_content


def test_variance_commentary_fallback_to_empty_after_exhausted_retries() -> None:
    variance = VarianceAnalysisResult(
        items=[
            _variance_item(
                "revenue",
                name="Revenue",
                direction="increase",
                variance_pct="19.05",
                is_material=True,
            )
        ]
    )
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("openai unavailable")
    sleep_calls: list[float] = []

    result = generate_variance_commentary(
        variance,
        openai_client=client,
        sleep=sleep_calls.append,
    )

    assert result == VarianceCommentaryResult(commentaries={})
    # 1 initial + 3 retries, all on gpt-4o — no gpt-4o-mini fallback.
    assert client.chat.completions.create.call_count == 4
    models = [
        call.kwargs["model"] for call in client.chat.completions.create.call_args_list
    ]
    assert models == ["gpt-4o"] * 4
    assert "gpt-4o-mini" not in models
    assert sleep_calls == [1, 2, 4]


# --- Business health --------------------------------------------------------


def test_business_health_prompt_contains_no_monetary_figures() -> None:
    current_sopl = [
        _line("revenue", "120000.00"),
        _line("cost_of_sales", "40000.00"),
        _line("operating_expenses", "30000.00"),
        _line("gross_profit", "80000.00", is_subtotal=True),
    ]
    prior_sopl = [
        _line("revenue", "100000.00"),
        _line("cost_of_sales", "45000.00"),
        _line("operating_expenses", "20000.00"),
        _line("gross_profit", "55000.00", is_subtotal=True),
    ]
    current_sofp = [
        _line("cash", "8000.00"),
        _line("loans", "10000.00"),
    ]
    prior_sofp = [
        _line("cash", "12000.00"),
        _line("loans", "10000.00"),
    ]

    client = MagicMock()
    client.chat.completions.create.return_value = _mock_completion(
        {
            "summary": "Margins improved while cash tightened.",
            "key_points": [
                "Gross margin improved",
                "Operating expenses grew faster than revenue",
                "Cash position declined",
            ],
            "confidence": "medium",
        }
    )

    result = generate_business_health_summary(
        current_sopl,
        prior_sopl,
        current_sofp,
        prior_sofp,
        openai_client=client,
        sleep=lambda _: None,
    )

    assert result.summary.startswith("Margins improved")
    assert len(result.key_points) == 3
    assert result.confidence == "medium"
    assert result.is_ai_generated is True

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["temperature"] == 0.2
    assert call_kwargs["messages"][0]["content"] == BUSINESS_HEALTH_SYSTEM
    user_content = call_kwargs["messages"][1]["content"]
    assert "Gross margin trend: improving" in user_content
    assert "Operating expense growth: faster than revenue" in user_content
    assert "Cash position: declining" in user_content
    assert "Debt levels: stable" in user_content
    for forbidden in ("120000", "100000", "40000", "8000", "£", "€", "$"):
        assert forbidden not in user_content


def test_business_health_fallback_to_empty_after_exhausted_retries() -> None:
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("openai unavailable")
    sleep_calls: list[float] = []

    result = generate_business_health_summary(
        [_line("revenue", "100.00")],
        [_line("revenue", "90.00")],
        [_line("cash", "10.00")],
        [_line("cash", "10.00")],
        openai_client=client,
        sleep=sleep_calls.append,
    )

    assert result.summary == ""
    assert result.key_points == []
    assert result.is_ai_generated is False
    assert client.chat.completions.create.call_count == 4
    models = [
        call.kwargs["model"] for call in client.chat.completions.create.call_args_list
    ]
    assert models == ["gpt-4o"] * 4
    assert "gpt-4o-mini" not in models
    assert sleep_calls == [1, 2, 4]
