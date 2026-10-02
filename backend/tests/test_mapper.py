"""Tests for hybrid account mapper Tiers 1–4."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.llm import MAPPING_TIE_BREAKER_SYSTEM
from app.services.mapper import (
    MappingResult,
    MappingTieBreakerTimeout,
    PriorConfirmedMapping,
    TIER4_OVERALL_TIMEOUT_SECONDS,
    TIER4_REQUEST_TIMEOUT_SECONDS,
    apply_llm_tie_breaker,
    map_accounts,
    map_accounts_with_llm,
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
    assert [r.confidence for r in results] == [Decimal("0.50")] * 4
    assert [r.canonical_line for r in results] == [
        "revenue",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
    ]


def test_tier3_7000_range_routes_amortisation_names_separately() -> None:
    """7000–7999 defaults to depreciation; amort*-named accounts → amortisation."""
    accounts = [
        FakeAccount(account_code="7000", account_name="Depreciation - Buildings"),
        FakeAccount(
            account_code="7010", account_name="Depreciation - Plant & Machinery"
        ),
        FakeAccount(account_code="7100", account_name="Amortisation - Software"),
        FakeAccount(account_code="7110", account_name="Amortisation - Goodwill"),
        FakeAccount(
            account_code="7120", account_name="Amortization of patents"
        ),  # US spelling
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.method for r in results] == ["code_range"] * 5
    assert [r.confidence for r in results] == [Decimal("0.50")] * 5
    assert [r.canonical_line for r in results] == [
        "depreciation",
        "depreciation",
        "amortisation",
        "amortisation",
        "amortisation",
    ]


def test_tier3_interest_polarity_income_vs_expense() -> None:
    """Interest names resolve by polarity; works in 4xxx and 7xxx bands."""
    accounts = [
        FakeAccount(account_code="7000", account_name="Interest Expense"),
        FakeAccount(account_code="7050", account_name="Bank Interest Paid"),
        FakeAccount(account_code="7060", account_name="Interest Charge"),
        FakeAccount(account_code="7900", account_name="Interest Income"),
        FakeAccount(account_code="4900", account_name="Interest Income"),
        FakeAccount(account_code="7000", account_name="Depreciation - Buildings"),
        FakeAccount(account_code="4000", account_name="Sales Revenue"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.method for r in results] == ["code_range"] * 7
    assert [r.canonical_line for r in results] == [
        "interest_expense",
        "interest_expense",
        "interest_expense",
        "interest_income",
        "interest_income",
        "depreciation",
        "revenue",
    ]


def test_tier3_accumulated_depreciation_maps_to_ppe_not_depreciation() -> None:
    """Accumulated Depreciation is a BS contra-asset → property_plant_equipment."""
    accounts = [
        FakeAccount(
            account_code="1450", account_name="Accumulated Depreciation - Buildings"
        ),
        FakeAccount(account_code="1460", account_name="Accumulated Depreciation"),
        FakeAccount(account_code="7000", account_name="Depreciation - Buildings"),
        FakeAccount(account_code="1450", account_name="Provision for Depreciation"),
        # Abbreviation variants that must still hit the BS-contra path (not P&L).
        FakeAccount(
            account_code="1210", account_name="Motor Vehicles - Accum. Depreciation"
        ),
        FakeAccount(
            account_code="1110", account_name="Plant & Machinery - Accum. Depreciation"
        ),
        FakeAccount(account_code="1210", account_name="Accum Depreciation - Vehicles"),
        FakeAccount(account_code="1210", account_name="Accum. Depn - Vehicles"),
        FakeAccount(
            account_code="1210", account_name="Acc. Depreciation - Motor Vehicles"
        ),
        FakeAccount(account_code="1210", account_name="A/Depn"),
        FakeAccount(account_code="1210", account_name="A/Depreciation"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.canonical_line for r in results] == [
        "property_plant_equipment",
        "property_plant_equipment",
        "depreciation",
        "property_plant_equipment",
        "property_plant_equipment",
        "property_plant_equipment",
        "property_plant_equipment",
        "property_plant_equipment",
        "property_plant_equipment",
        "property_plant_equipment",
        "property_plant_equipment",
    ]
    assert results[0].method == "code_range"
    assert results[2].method == "code_range"
    assert results[4].method == "code_range"
    assert results[9].method == "code_range"


def test_bare_depreciation_charge_is_not_treated_as_bs_contra() -> None:
    """P&L depreciation/depn charges must not match the Accum/Acc/A-slash contra cues."""
    accounts = [
        FakeAccount(account_code="7000", account_name="Depreciation"),
        FakeAccount(account_code="7020", account_name="Depreciation - Motor Vehicles"),
        FakeAccount(account_code="7020", account_name="Depn - Vehicles"),
        FakeAccount(account_code="7100", account_name="Amortisation - Software"),
    ]
    results = map_accounts(accounts, prior_confirmed=[])
    assert results[0].canonical_line == "depreciation"
    assert results[1].canonical_line == "depreciation"
    # Bare Depn with no 7000–7999 specialisation beyond band default
    assert results[2].canonical_line == "depreciation"
    assert results[3].canonical_line == "amortisation"
    assert all(r.canonical_line != "property_plant_equipment" for r in results)
    assert all(r.canonical_line != "intangible_assets" for r in results)


def test_tier3_accumulated_amortisation_maps_to_intangibles_not_amortisation() -> None:
    """Accumulated Amortisation is a BS contra-asset → intangible_assets."""
    accounts = [
        FakeAccount(
            account_code="1550", account_name="Accumulated Amortisation - Software"
        ),
        FakeAccount(account_code="7100", account_name="Amortisation - Software"),
        FakeAccount(account_code="1550", account_name="Provision for Amortisation"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.canonical_line for r in results] == [
        "intangible_assets",
        "amortisation",
        "intangible_assets",
    ]


def test_allowance_for_doubtful_debts_nets_trade_receivables() -> None:
    """Same contra-name bug class as Accum. Dep → PPE; leaf is trade_receivables."""
    accounts = [
        FakeAccount(account_code="1610", account_name="Allowance for Doubtful Debts"),
        FakeAccount(account_code="1610", account_name="Provision for Doubtful Debts"),
        FakeAccount(account_code="1610", account_name="Provision for Bad Debts"),
        FakeAccount(
            account_code="1610", account_name="Allowance for Expected Credit Losses"
        ),
        FakeAccount(account_code="1600", account_name="Trade Debtors"),
        FakeAccount(account_code="6500", account_name="Bad Debts Written Off"),
        FakeAccount(account_code="6500", account_name="Bad Debt Expense"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.canonical_line for r in results] == [
        "trade_receivables",
        "trade_receivables",
        "trade_receivables",
        "trade_receivables",
        None,  # 1000–3999 SOFP cost/debtor rows fall through without Tier 4
        "operating_expenses",
        "operating_expenses",
    ]
    assert all(r.method == "code_range" for r in results[:4])
    assert all(r.canonical_line != "trade_receivables" for r in results[5:])


def test_vat_recoverable_maps_to_other_receivables_not_taxes_payable() -> None:
    """VAT Recoverable → other_receivables; VAT Payable stays for Tier 4 / taxes."""
    accounts = [
        FakeAccount(account_code="1800", account_name="VAT Recoverable"),
        FakeAccount(account_code="1800", account_name="VAT Receivable"),
        FakeAccount(account_code="2200", account_name="VAT Payable"),
    ]
    results = map_accounts(accounts, prior_confirmed=[])
    assert [r.canonical_line for r in results] == [
        "other_receivables",
        "other_receivables",
        None,
    ]
    assert [r.method for r in results] == ["code_range", "code_range", None]


def test_tier3_6000_range_routes_depreciation_names_to_depreciation() -> None:
    """6000–6999 + depreciation name → depreciation; other opex names unchanged."""
    accounts = [
        FakeAccount(account_code="6400", account_name="Depreciation"),
        FakeAccount(account_code="6410", account_name="Depreciation Expense"),
        FakeAccount(account_code="6100", account_name="Rent & Rates"),
        FakeAccount(account_code="6500", account_name="Bank Charges"),
        FakeAccount(account_code="6550", account_name="Bad Debts Written Off"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.method for r in results] == ["code_range"] * 5
    assert [r.canonical_line for r in results] == [
        "depreciation",
        "depreciation",
        "operating_expenses",
        "operating_expenses",
        "operating_expenses",
    ]


def test_tier3_name_contradiction_falls_through_for_non_appendix_c_coa() -> None:
    """Option B: clear name-vs-band conflict → method=None (Tier 4), not wrong line."""
    accounts = [
        FakeAccount(account_code="7100", account_name="Rent - Office Premises"),
        FakeAccount(
            account_code="7600", account_name="Bank Charges & Transaction Fees"
        ),
        FakeAccount(
            account_code="4000", account_name="Called Up Share Capital - Ordinary"
        ),
        FakeAccount(account_code="4010", account_name="Share Premium Account"),
        FakeAccount(
            account_code="4100", account_name="Retained Earnings - Brought Forward"
        ),
        FakeAccount(
            account_code="5000", account_name="Sales - Manufactured Goods Domestic"
        ),
        FakeAccount(account_code="6000", account_name="Cost of Sales - Materials Used"),
        # Appendix-C-aligned controls in the same bands must still hit code_range:
        FakeAccount(account_code="4200", account_name="Sales Revenue"),
        FakeAccount(account_code="5500", account_name="Purchases"),
        FakeAccount(account_code="6100", account_name="Rent & Rates"),
        FakeAccount(account_code="7000", account_name="Depreciation - Buildings"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.method for r in results[:7]] == [None] * 7
    assert all(r.canonical_line is None for r in results[:7])
    assert [r.method for r in results[7:]] == ["code_range"] * 4
    assert [r.canonical_line for r in results[7:]] == [
        "revenue",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
    ]
    assert all(r.confidence == Decimal("0.50") for r in results[7:])


def test_tier3_impairment_interest_receivable_associate_fall_through() -> None:
    """Stress-found cases: do not confidently mis-file via code_range defaults."""
    accounts = [
        FakeAccount(
            account_code="5000",
            account_name="Impairment of investment in Beta",
        ),
        FakeAccount(
            account_code="5100",
            account_name="Impairment of goodwill — Beta",
        ),
        FakeAccount(
            account_code="6100",
            account_name="Interest receivable — intercompany",
        ),
        FakeAccount(
            account_code="4200",
            account_name="Share of profit of associate Gamma",
        ),
        # Controls that must still resolve:
        FakeAccount(account_code="5500", account_name="Purchases"),
        FakeAccount(account_code="4000", account_name="Sales Revenue"),
        FakeAccount(account_code="7000", account_name="Interest Expense"),
        FakeAccount(account_code="7900", account_name="Interest Income"),
    ]

    results = map_accounts(accounts, prior_confirmed=[])

    assert [r.method for r in results[:4]] == [None] * 4
    assert all(r.canonical_line is None for r in results[:4])
    assert [r.canonical_line for r in results[4:]] == [
        "cost_of_sales",
        "revenue",
        "interest_expense",
        "interest_income",
    ]
    assert [r.method for r in results[4:]] == ["code_range"] * 4


def test_ambiguous_and_invalid_codes_fall_through_unmapped() -> None:
    accounts = [
        FakeAccount(account_code="1500", account_name="Cash at bank"),  # assets
        FakeAccount(account_code="2100", account_name="Trade payables"),  # liabilities
        FakeAccount(account_code="3100", account_name="Share capital"),  # equity
        FakeAccount(account_code="8100", account_name="Interest paid"),  # interest/tax
        FakeAccount(account_code="ABC-100", account_name="Suspense"),  # non-numeric
        FakeAccount(
            account_code="10000", account_name="Out of range"
        ),  # outside 1000–9999
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
                {
                    "index": 1,
                    "canonical_line": "cash",
                    "reasoning": "Bank balance",
                    "confidence": 0.92,
                },
                {
                    "index": 2,
                    "canonical_line": "trade_payables",
                    "reasoning": "Creditors",
                    "confidence": 0.88,
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
        MappingResult("1500", "Cash at bank", "cash", Decimal("0.92"), "llm"),
        MappingResult(
            "2100", "Trade creditors", "trade_payables", Decimal("0.88"), "llm"
        ),
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
    assert '"confidence": 0.0' in MAPPING_TIE_BREAKER_SYSTEM
    assert "taxes_payable" in MAPPING_TIE_BREAKER_SYSTEM
    assert "social_security_payable" in MAPPING_TIE_BREAKER_SYSTEM
    assert "Prefer the most specific matching line" in MAPPING_TIE_BREAKER_SYSTEM
    assert "VAT control" in MAPPING_TIE_BREAKER_SYSTEM
    assert "PAYE/NI control" in MAPPING_TIE_BREAKER_SYSTEM
    assert "not tax or PAYE/NI control accounts" in MAPPING_TIE_BREAKER_SYSTEM
    user_content = call_kwargs["messages"][1]["content"]
    assert "Code: 1500, Name: Cash at bank" in user_content
    assert "Code: 2100, Name: Trade creditors" in user_content
    assert "£" not in user_content
    # User prompt must still carry no monetary amounts / confidence scores —
    # confidence belongs in the system schema + model response only.
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
                    "confidence": 0.35,
                }
            ]
        }
    )

    results = apply_llm_tie_breaker(
        unmapped, openai_client=client, sleep=lambda _: None
    )

    assert results == [
        MappingResult("9000", "Misc clearing", None, Decimal("0.35"), "llm"),
    ]


def test_tier4_retry_then_succeed() -> None:
    unmapped = [MappingResult("1500", "Cash at bank", None, None, None)]
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        RuntimeError("temporary outage"),
        _mock_completion(
            {
                "mappings": [
                    {
                        "index": 1,
                        "canonical_line": "cash",
                        "reasoning": "Cash account",
                        "confidence": 0.9,
                    }
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

    assert results == [
        MappingResult("1500", "Cash at bank", "cash", Decimal("0.90"), "llm")
    ]
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


def test_tier4_parses_and_clamps_self_reported_confidence() -> None:
    from app.services.mapper import _parse_llm_confidence, _parse_llm_mappings

    assert _parse_llm_confidence(0.923) == Decimal("0.92")
    assert _parse_llm_confidence("1.5") == Decimal("1.00")
    assert _parse_llm_confidence(-0.2) == Decimal("0.00")
    assert _parse_llm_confidence("not-a-number") is None
    assert _parse_llm_confidence(None) is None

    unmapped = [MappingResult("1100", "Cash", None, None, None)]
    results = _parse_llm_mappings(
        unmapped,
        {
            "mappings": [
                {
                    "index": 1,
                    "canonical_line": "cash",
                    "reasoning": "Cash",
                    "confidence": "0.955",
                }
            ]
        },
    )
    assert results[0].confidence == Decimal("0.96")
    assert results[0].method == "llm"


def test_bad_debt_expense_7100_resolves_to_operating_expenses() -> None:
    """Code 7100 is a depreciation band; the name is an operating expense.

    The tie-break must not store other_revenue or unmapped. There is no
    separate bad-debt expense canonical line, so operating_expenses is the
    line. Repeated hostile model answers stay corrected.
    """
    assert "Bad Debt Expense" in MAPPING_TIE_BREAKER_SYSTEM
    assert "not other_revenue, and not unmapped" in MAPPING_TIE_BREAKER_SYSTEM
    assert "Never use other_revenue or revenue for a name that says Expense" in (
        MAPPING_TIE_BREAKER_SYSTEM
    )

    account = FakeAccount(account_code="7100", account_name="Bad Debt Expense")
    # No prior mappings: the depreciation band rejects the name and Tier 4 runs.
    assert map_accounts([account], prior_confirmed=[])[0].method is None

    hostile_answers = (
        ("other_revenue", 0.80),
        ("unmapped", 0.70),
        ("revenue", 0.60),
        ("depreciation", 0.55),
        ("operating_expenses", 0.95),
    )
    for canonical_line, confidence in hostile_answers:
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_completion(
            {
                "mappings": [
                    {
                        "index": 1,
                        "canonical_line": canonical_line,
                        "reasoning": "model guess",
                        "confidence": confidence,
                    }
                ]
            }
        )
        result = map_accounts_with_llm(
            [account],
            prior_confirmed=[],
            openai_client=client,
            sleep=lambda _: None,
        )[0]
        assert result.canonical_line == "operating_expenses"
        assert result.canonical_line != "other_revenue"
        assert result.method == "llm"
        if canonical_line == "operating_expenses":
            assert result.confidence == Decimal("0.95")
        else:
            assert result.confidence == Decimal("0.90")


def test_expense_guard_does_not_rewrite_unrelated_accounts() -> None:
    """The Bad Debt Expense guard must not move accounts that lack the word Expense.

    These five were correct before the guard and were forced onto the wrong
    line because the guard reused broad keyword lists (corporation tax, software
    licences, materials, motor, PRSI).
    """
    cases = (
        ("2400", "Corporation Tax Payable", "taxes_payable"),
        ("1400", "Intangible Assets - Software Licences", "intangible_assets"),
        ("1500", "Inventory - Raw Materials", "inventory"),
        ("1200", "Motor Vehicles - Cost", "property_plant_equipment"),
        ("2300", "PAYE/PRSI Control", "social_security_payable"),
    )
    for code, name, line in cases:
        client = MagicMock()
        client.chat.completions.create.return_value = _mock_completion(
            {
                "mappings": [
                    {
                        "index": 1,
                        "canonical_line": line,
                        "reasoning": "correct model answer",
                        "confidence": 0.91,
                    }
                ]
            }
        )
        result = map_accounts_with_llm(
            [FakeAccount(account_code=code, account_name=name)],
            prior_confirmed=[],
            openai_client=client,
            sleep=lambda _: None,
        )[0]
        assert result.canonical_line == line
        assert result.method == "llm"
        assert result.confidence == Decimal("0.91")


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _batch_payload(count: int) -> dict[str, object]:
    return {
        "mappings": [
            {
                "index": index,
                "canonical_line": "operating_expenses",
                "reasoning": "overhead",
                "confidence": 0.8,
            }
            for index in range(1, count + 1)
        ]
    }


def test_tier4_batch_logs_send_retries_and_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Forty accounts, two failed attempts, then a successful batch."""
    count = 40
    unmapped = [
        MappingResult(str(5000 + index), f"Sundry overhead {index}", None, None, None)
        for index in range(1, count + 1)
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        RuntimeError("temporary outage"),
        RuntimeError("still unavailable"),
        _mock_completion(_batch_payload(count)),
    ]
    clock = _Clock()
    with caplog.at_level(logging.INFO, logger="app.services.mapper"):
        results = apply_llm_tie_breaker(
            unmapped,
            openai_client=client,
            sleep=clock.sleep,
            clock=clock,
        )

    assert len(results) == count
    assert all(result.canonical_line == "operating_expenses" for result in results)
    assert client.chat.completions.create.call_count == 3
    assert [
        call.kwargs["timeout"] for call in client.chat.completions.create.call_args_list
    ] == [
        TIER4_REQUEST_TIMEOUT_SECONDS,
        TIER4_REQUEST_TIMEOUT_SECONDS,
        TIER4_REQUEST_TIMEOUT_SECONDS,
    ]
    text = caplog.text
    assert "Tier 4 mapping batch sent: 40 accounts; overall deadline 480s" in text
    assert "model=gpt-4o-mini attempt=1/4 request_timeout=180s accounts=40" in text
    assert (
        "Tier 4 mapping retry: model=gpt-4o-mini attempt=1/4 failed "
        "(temporary outage); waiting 1s" in text
    )
    assert "model=gpt-4o-mini attempt=2/4 request_timeout=180s accounts=40" in text
    assert (
        "Tier 4 mapping retry: model=gpt-4o-mini attempt=2/4 failed "
        "(still unavailable); waiting 2s" in text
    )
    assert "model=gpt-4o-mini attempt=3/4 request_timeout=180s accounts=40" in text
    assert (
        "Tier 4 mapping outcome: success model=gpt-4o-mini attempt=3/4 accounts=40"
        in text
    )


def test_tier4_overall_deadline_fails_the_job(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The combined budget stops the batch instead of waiting out every retry."""
    unmapped = [
        MappingResult(str(6000 + index), f"Clearing account {index}", None, None, None)
        for index in range(1, 13)
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("hung upstream")
    clock = _Clock()
    with caplog.at_level(logging.INFO, logger="app.services.mapper"):
        with pytest.raises(
            MappingTieBreakerTimeout, match="timed out after 3s"
        ) as raised:
            apply_llm_tie_breaker(
                unmapped,
                openai_client=client,
                sleep=clock.sleep,
                clock=clock,
                overall_timeout_seconds=3,
            )
    assert "The tie-breaker did not finish." in str(raised.value)
    text = caplog.text
    assert "Tier 4 mapping batch sent: 12 accounts; overall deadline 3s" in text
    assert "request_timeout=3s" in text
    assert "waiting 1s" in text
    assert "Tier 4 mapping outcome: timed out" in text
    assert "leaving accounts unmapped" not in text
    assert TIER4_OVERALL_TIMEOUT_SECONDS == 480.0
