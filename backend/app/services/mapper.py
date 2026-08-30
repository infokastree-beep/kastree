"""Hybrid account mapper — Tiers 1–3 (exact, fuzzy, code-range).

Tier 4 (LLM tie-breaker) is intentionally not implemented here. Accounts that
fall through all three deterministic tiers are returned with
canonical_line=None, confidence=None, method=None so a later Tier 4 pass can
pick them up.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol, Sequence

from rapidfuzz.distance import Levenshtein
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account_mapping import AccountMapping

MappingMethod = Literal["exact", "fuzzy", "code_range"]

FUZZY_THRESHOLD = Decimal("0.85")
# Absorb float noise from rapidfuzz so equal Levenshtein scores stay tied.
FUZZY_RATIO_TIE_TOLERANCE = Decimal("1e-9")
CODE_RANGE_CONFIDENCE = Decimal("0.65")
EXACT_CONFIDENCE = Decimal("1.00")

# Appendix C ranges that resolve to exactly one canonical line.
UNAMBIGUOUS_CODE_RANGES: tuple[tuple[int, int, str], ...] = (
    (4000, 4999, "revenue"),
    (5000, 5999, "cost_of_sales"),
    (6000, 6999, "operating_expenses"),
    (7000, 7999, "depreciation"),
)


@dataclass(frozen=True)
class PriorConfirmedMapping:
    """A previously confirmed mapping for the same client (Tier 1/2 input)."""

    source_code: str
    source_name: str
    canonical_line: str


@dataclass(frozen=True)
class MappingResult:
    source_code: str
    source_name: str
    canonical_line: str | None
    confidence: Decimal | None
    method: MappingMethod | None


class MappableAccount(Protocol):
    """Anything with account identifiers (e.g. TBRow)."""

    account_code: str
    account_name: str


def normalize_text(value: str | None) -> str:
    """Case-insensitive, whitespace-normalized comparison key."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def fetch_confirmed_mappings(
    session: Session,
    client_id: uuid.UUID,
) -> list[PriorConfirmedMapping]:
    """Load confirmed prior mappings for Tier 1/2 (Product Spec §4.2)."""
    statement = (
        select(AccountMapping)
        .where(
            AccountMapping.client_id == client_id,
            AccountMapping.is_confirmed.is_(True),
        )
        .order_by(AccountMapping.created_at)
    )
    rows = session.scalars(statement).all()
    return [
        PriorConfirmedMapping(
            source_code=row.source_code or "",
            source_name=row.source_name,
            canonical_line=row.canonical_line,
        )
        for row in rows
    ]


def map_accounts_for_client(
    session: Session,
    client_id: uuid.UUID,
    accounts: Sequence[MappableAccount],
) -> list[MappingResult]:
    """Map accounts for a client using prior confirmed mappings from the DB."""
    prior = fetch_confirmed_mappings(session, client_id)
    return map_accounts(accounts, prior)


def map_accounts(
    accounts: Sequence[MappableAccount],
    prior_confirmed: Sequence[PriorConfirmedMapping],
) -> list[MappingResult]:
    """Run Tiers 1–3 for each account.

    Results with method=None fell through all deterministic tiers and are ready
    for Tier 4 (LLM tie-breaker).
    """
    return [_map_one(account, prior_confirmed) for account in accounts]


def _map_one(
    account: MappableAccount,
    prior_confirmed: Sequence[PriorConfirmedMapping],
) -> MappingResult:
    source_code = account.account_code
    source_name = account.account_name

    exact = _tier1_exact(source_code, source_name, prior_confirmed)
    if exact is not None:
        return exact

    fuzzy = _tier2_fuzzy(source_code, source_name, prior_confirmed)
    if fuzzy is not None:
        return fuzzy

    code_range = _tier3_code_range(source_code, source_name)
    if code_range is not None:
        return code_range

    return MappingResult(
        source_code=source_code,
        source_name=source_name,
        canonical_line=None,
        confidence=None,
        method=None,
    )


def _tier1_exact(
    source_code: str,
    source_name: str,
    prior_confirmed: Sequence[PriorConfirmedMapping],
) -> MappingResult | None:
    code_key = normalize_text(source_code)
    name_key = normalize_text(source_name)

    for prior in prior_confirmed:
        if (
            normalize_text(prior.source_code) == code_key
            and normalize_text(prior.source_name) == name_key
        ):
            return MappingResult(
                source_code=source_code,
                source_name=source_name,
                canonical_line=prior.canonical_line,
                confidence=EXACT_CONFIDENCE,
                method="exact",
            )
    return None


def _tier2_fuzzy(
    source_code: str,
    source_name: str,
    prior_confirmed: Sequence[PriorConfirmedMapping],
) -> MappingResult | None:
    if not prior_confirmed:
        return None

    name_key = normalize_text(source_name)
    scored: list[tuple[Decimal, str]] = []
    for prior in prior_confirmed:
        ratio = Decimal(
            str(Levenshtein.normalized_similarity(name_key, normalize_text(prior.source_name)))
        )
        scored.append((ratio, prior.canonical_line))

    best_ratio = max(ratio for ratio, _ in scored)
    if best_ratio < FUZZY_THRESHOLD:
        return None

    tied_canonical_lines = {
        canonical_line
        for ratio, canonical_line in scored
        if best_ratio - ratio <= FUZZY_RATIO_TIE_TOLERANCE
    }
    if len(tied_canonical_lines) != 1:
        # Genuine ambiguity across distinct canonical lines — leave for Tier 4.
        return None

    confidence = best_ratio.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return MappingResult(
        source_code=source_code,
        source_name=source_name,
        canonical_line=next(iter(tied_canonical_lines)),
        confidence=confidence,
        method="fuzzy",
    )


def _tier3_code_range(source_code: str, source_name: str) -> MappingResult | None:
    code_int = _parse_account_code(source_code)
    if code_int is None:
        return None

    for start, end, canonical_line in UNAMBIGUOUS_CODE_RANGES:
        if start <= code_int <= end:
            return MappingResult(
                source_code=source_code,
                source_name=source_name,
                canonical_line=canonical_line,
                confidence=CODE_RANGE_CONFIDENCE,
                method="code_range",
            )
    return None


def _parse_account_code(source_code: str) -> int | None:
    text = source_code.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None
