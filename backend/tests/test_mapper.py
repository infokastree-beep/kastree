"""Tests for hybrid account mapper Tiers 1–4."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.llm import MAPPING_TIE_BREAKER_SYSTEM
from app.services.mapper import (
    MappingResult,
    PriorConfirmedMapping,
    apply_llm_tie_breaker,
    map_accounts,
)


@dataclass(frozen=True)
class FakeAccount:
    account_code: str
    account_name: str


def test_tier1_exact_match_hit() -> None:
    prior = [
        PriorConfirmedMapping(
            source_code="4000",
            source_name="Sales Revenue",
            canonical_line="revenue",
        )
    ]
    accounts = [FakeAccount(account_code="4000", account_name="  SALES   REVENUE ")]

    results = map_accounts(accounts, prior)

    assert results == [
        MappingResult(
            source_code="4000",
            source_name="  SALES   REVENUE ",
            canonical_line="revenue",
            confidence=Decimal("1.00"),
            method="exact",
        )
    ]


def test_tier2_fuzzy_match_at_exactly_0_85_threshold() -> None:
    # Levenshtein.normalized_similarity("a"*100, "b"*15+"a"*85) == 0.85
    prior_name = "a" * 100
    new_name = ("b" * 15) + ("a" * 85)
    prior = [
        PriorConfirmedMapping(
            source_code="9999",
            source_name=prior_name,
            canonical_line="revenue",
        )
    ]
    accounts = [FakeAccount(account_code="4100", account_name=new_name)]

    results = map_accounts(accounts, prior)

    assert len(results) == 1
    assert results[0].method == "fuzzy"
    assert results[0].canonical_line == "revenue"
    assert results[0].confidence == Decimal("0.85")


def test_tier2_fuzzy_match_just_below_threshold_does_not_match() -> None:
    # Levenshtein.normalized_similarity("a"*100, "b"*16+"a"*84) == 0.84
    # Falls through fuzzy; code 4100 then hits Tier 3 revenue — use ambiguous
    # asset range so failure to fuzzy-match leaves the account unmapped.
    prior_name = "a" * 100
    new_name = ("b" * 16) + ("a" * 84)
    prior = [
        PriorConfirmedMapping(
            source_code="9999",
            source_name=prior_name,
            canonical_line="revenue",
        )
    ]
    accounts = [FakeAccount(account_code="1100", account_name=new_name)]

    results = map_accounts(accounts, prior)

    assert results == [
        MappingResult(
            source_code="1100",
            source_name=new_name,
            canonical_line=None,
            confidence=None,
            method=None,
        )
    ]


def test_tier2_fuzzy_ambiguous_tie_falls_through_unmapped() -> None:
    # Same prior name → equal fuzzy ratio; different canonical lines → ambiguous.
    # Asset-range code so Tier 3 cannot resolve after the fuzzy fall-through.
    prior = [
        PriorConfirmedMapping(
            source_code="4001",
            source_name="Widget Sales",
            canonical_line="revenue",
        ),
        PriorConfirmedMapping(
            source_code="5001",
            source_name="Widget Sales",
            canonical_line="cost_of_sales",
        ),
    ]
    accounts = [FakeAccount(account_code="1100", account_name="Widget Sales")]

    results = map_accounts(accounts, prior)

    assert results == [
        MappingResult(
            source_code="1100",
            source_name="Widget Sales",
            canonical_line=None,
            confidence=None,
            method=None,
        )
    ]


def test_tier2_fuzzy_tie_with_same_canonical_line_still_maps() -> None:
    prior = [
        PriorConfirmedMapping(
            source_code="4001",
            source_name="Widget Sales",
            canonical_line="revenue",
        ),
        PriorConfirmedMapping(
            source_code="4002",
            source_name="Widget Sales",
            canonical_line="revenue",
        ),
    ]
    accounts = [FakeAccount(account_code="1100", account_name="Widget Sales")]

    results = map_accounts(accounts, prior)

    assert results == [
        MappingResult(
            source_code="1100",
            source_name="Widget Sales",
            canonical_line="revenue",
            confidence=Decimal("1.00"),
            method="fuzzy",
        )
    ]


def test_tier3_code_range_unambiguous_hits() -> None:
    accounts = [
        FakeAccount(account_code="4000", account_name="Sales"),
        FakeAccount(account_code="5500", account_name="Purchases"),
        FakeAccount(account_code="6100", account_name="Rent"),
        FakeAccount(account_code="7999", account_name="Depreciation charge"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.method for r in results] == ["code_range"] * 4
    assert [r.confidence for r in results] == [Decimal("0.65")] * 4
    assert [r.canonical_line for r in results] == [
        "revenue",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
    ]


def test_ambiguous_and_invalid_codes_fall_through_unmapped() -> None:
    accounts = [
        FakeAccount(account_code="1500", account_name="Cash at bank"),  # assets
        FakeAccount(account_code="2100", account_name="Trade payables"),  # liabilities
        FakeAccount(account_code="3100", account_name="Share capital"),  # equity
        FakeAccount(account_code="8100", account_name="Interest paid"),  # interest/tax
        FakeAccount(account_code="ABC-100", account_name="Suspense"),  # non-numeric
        FakeAccount(account_code="10000", account_name="Out of range"),  # outside 1000–9999
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert all(result.method is None for result in results)
    assert all(result.canonical_line is None for result in results)
    assert all(result.confidence is None for result in results)
    assert [result.source_code for result in results] == [
        "1500",
        "2100",
        "3100",
        "8100",
        "ABC-100",
        "10000",
    ]


def _mock_completion(payload: dict) -> MagicMock:
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def test_tier4_successful_batch_mapping_response() -> None:
    unmapped = [
        MappingResult("1500", "Cash at bank", None, None, None),
        MappingResult("2100", "Trade creditors", None, None, None),
    ]
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_completion(
        {
            "mappings": [
                {"index": 1, "canonical_line": "cash", "reasoning": "Bank balance"},
                {
                    "index": 2,
                    "canonical_line": "trade_payables",
                    "reasoning": "Creditors",
                },
            ]
        }
    )
    sleep_calls: list[float] = []

    results = apply_llm_tie_breaker(
        unmapped,
        openai_client=client,
        sleep=sleep_calls.append,
    )

    assert results == [
        MappingResult("1500", "Cash at bank", "cash", None, "llm"),
        MappingResult("2100", "Trade creditors", "trade_payables", None, "llm"),
    ]
    assert sleep_calls == []

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["temperature"] == 0.1
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert call_kwargs["messages"][0] == {
        "role": "system",
        "content": MAPPING_TIE_BREAKER_SYSTEM,
    }
    user_content = call_kwargs["messages"][1]["content"]
    assert "Code: 1500, Name: Cash at bank" in user_content
    assert "Code: 2100, Name: Trade creditors" in user_content
    assert "£" not in user_content
    assert "confidence" not in user_content.lower()


def test_tier4_unmapped_response_path() -> None:
    unmapped = [MappingResult("9000", "Misc clearing", None, None, None)]
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_completion(
        {
            "mappings": [
                {
                    "index": 1,
                    "canonical_line": "unmapped",
                    "reasoning": "Genuinely unclear",
                }
            ]
        }
    )

    results = apply_llm_tie_breaker(unmapped, openai_client=client, sleep=lambda _: None)

    assert results == [
        MappingResult("9000", "Misc clearing", None, None, "llm"),
    ]


def test_tier4_retry_then_succeed() -> None:
    unmapped = [MappingResult("1500", "Cash at bank", None, None, None)]
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        RuntimeError("temporary outage"),
        _mock_completion(
            {
                "mappings": [
                    {"index": 1, "canonical_line": "cash", "reasoning": "Cash account"}
                ]
            }
        ),
    ]
    sleep_calls: list[float] = []

    results = apply_llm_tie_breaker(
        unmapped,
        openai_client=client,
        sleep=sleep_calls.append,
    )

    assert results == [MappingResult("1500", "Cash at bank", "cash", None, "llm")]
    assert client.chat.completions.create.call_count == 2
    assert sleep_calls == [1]


def test_tier4_fallback_to_gpt4o_then_give_up_leaves_unmapped() -> None:
    unmapped = [
        MappingResult("1500", "Cash at bank", None, None, None),
        MappingResult("3100", "Share capital", None, None, None),
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("openai unavailable")
    sleep_calls: list[float] = []

    results = apply_llm_tie_breaker(
        unmapped,
        openai_client=client,
        sleep=sleep_calls.append,
    )

    assert results == list(unmapped)
    assert all(result.method is None for result in results)
    # 1 initial + 3 retries on gpt-4o-mini, then the same on gpt-4o
    assert client.chat.completions.create.call_count == 8
    models = [
        call.kwargs["model"] for call in client.chat.completions.create.call_args_list
    ]
    assert models == ["gpt-4o-mini"] * 4 + ["gpt-4o"] * 4
    assert sleep_calls == [1, 2, 4, 1, 2, 4]

