"""Tests for hybrid account mapper Tiers 1–3."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.mapper import (
    MappingResult,
    PriorConfirmedMapping,
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
