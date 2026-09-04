"""Hybrid account mapper — Tiers 1–4 (exact, fuzzy, code-range, LLM).

Tier 4 (LLM tie-breaker) runs only on accounts that fell through Tiers 1–3
(method=None). On LLM outage after the mini→4o fallback chain, those accounts
remain method=None rather than failing the whole mapping request.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Literal, Protocol, Sequence

from openai import OpenAI
from rapidfuzz.distance import Levenshtein
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account_mapping import AccountMapping
from app.services.llm import (
    MAPPING_TIE_BREAKER_CANONICAL_LINES,
    MAPPING_TIE_BREAKER_SYSTEM,
)

logger = logging.getLogger(__name__)

MappingMethod = Literal["exact", "fuzzy", "code_range", "llm"]

FUZZY_THRESHOLD = Decimal("0.85")
# Absorb float noise from rapidfuzz so equal Levenshtein scores stay tied.
FUZZY_RATIO_TIE_TOLERANCE = Decimal("1e-9")
CODE_RANGE_CONFIDENCE = Decimal("0.65")
EXACT_CONFIDENCE = Decimal("1.00")

LLM_PRIMARY_MODEL = "gpt-4o-mini"
LLM_FALLBACK_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0.1
# 1 initial attempt + 3 retries (Section 7.1: "3 retries with exponential backoff").
LLM_MAX_ATTEMPTS = 4
LLM_BACKOFF_SECONDS = (1, 2, 4)

# Appendix C ranges that resolve to exactly one canonical line.
# 7000–7999 defaults to depreciation; names containing "amort…" are specialised
# to amortisation inside _tier3_code_range (range alone cannot split those concepts).
UNAMBIGUOUS_CODE_RANGES: tuple[tuple[int, int, str], ...] = (
    (4000, 4999, "revenue"),
    (5000, 5999, "cost_of_sales"),
    (6000, 6999, "operating_expenses"),
    (7000, 7999, "depreciation"),
)

SleepFn = Callable[[float], None]


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
    company_id: uuid.UUID,
) -> list[PriorConfirmedMapping]:
    """Load confirmed prior mappings for Tier 1/2 (Product Spec §4.2)."""
    statement = (
        select(AccountMapping)
        .where(
            AccountMapping.company_id == company_id,
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


def map_accounts_for_company(
    session: Session,
    company_id: uuid.UUID,
    accounts: Sequence[MappableAccount],
    *,
    openai_client: OpenAI | None = None,
    sleep: SleepFn = time.sleep,
) -> list[MappingResult]:
    """Map accounts for a company through Tiers 1–4."""
    prior = fetch_confirmed_mappings(session, company_id)
    return map_accounts_with_llm(
        accounts,
        prior,
        openai_client=openai_client,
        sleep=sleep,
    )


# Backward-compatible alias for callers not yet renamed.
map_accounts_for_client = map_accounts_for_company


def map_accounts(
    accounts: Sequence[MappableAccount],
    prior_confirmed: Sequence[PriorConfirmedMapping],
) -> list[MappingResult]:
    """Run Tiers 1–3 for each account.

    Results with method=None fell through all deterministic tiers and are ready
    for Tier 4 (LLM tie-breaker).
    """
    return [_map_one(account, prior_confirmed) for account in accounts]


def map_accounts_with_llm(
    accounts: Sequence[MappableAccount],
    prior_confirmed: Sequence[PriorConfirmedMapping],
    *,
    openai_client: OpenAI | None = None,
    sleep: SleepFn = time.sleep,
) -> list[MappingResult]:
    """Run Tiers 1–3, then Tier 4 LLM tie-breaker on any remaining unmapped accounts."""
    results = map_accounts(accounts, prior_confirmed)
    return apply_llm_tie_breaker(results, openai_client=openai_client, sleep=sleep)


def apply_llm_tie_breaker(
    results: Sequence[MappingResult],
    *,
    openai_client: OpenAI | None = None,
    sleep: SleepFn = time.sleep,
) -> list[MappingResult]:
    """Apply Tier 4 to results with method=None; leave other results unchanged.

    Never raises on LLM failure — exhausted fallbacks leave those accounts as
    method=None (Section 7.1).
    """
    unmapped_indexes = [index for index, result in enumerate(results) if result.method is None]
    if not unmapped_indexes:
        return list(results)

    unmapped = [results[index] for index in unmapped_indexes]
    llm_mapped = _llm_map_batch(unmapped, openai_client=openai_client, sleep=sleep)

    merged = list(results)
    for index, mapped in zip(unmapped_indexes, llm_mapped, strict=True):
        merged[index] = mapped
    return merged


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
            resolved = canonical_line
            # 7000–7999 is shared by depreciation and amortisation P&L charges.
            # Distinguish by name so amortisation-named rows do not lock to
            # depreciation at Tier 3 and never reach Tier 4.
            if (
                start == 7000
                and end == 7999
                and _name_suggests_amortisation(source_name)
            ):
                resolved = "amortisation"
            return MappingResult(
                source_code=source_code,
                source_name=source_name,
                canonical_line=resolved,
                confidence=CODE_RANGE_CONFIDENCE,
                method="code_range",
            )
    return None


def _name_suggests_amortisation(source_name: str) -> bool:
    """True when the account name clearly indicates amortisation (not depreciation)."""
    normalized = normalize_text(source_name)
    return bool(re.search(r"\bamort", normalized))


def _parse_account_code(source_code: str) -> int | None:
    text = source_code.strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _llm_map_batch(
    unmapped: Sequence[MappingResult],
    *,
    openai_client: OpenAI | None,
    sleep: SleepFn,
) -> list[MappingResult]:
    try:
        client = openai_client if openai_client is not None else OpenAI()
    except Exception as init_error:
        # Missing OPENAI_API_KEY (or other client config) — Tier 4 was attempted
        # but cannot run; leave method=None for the caller to persist as llm/unmapped.
        logger.error(
            "OpenAI client init failed for mapping tie-breaker: %s; leaving accounts unmapped",
            init_error,
        )
        return list(unmapped)

    user_prompt = _build_tie_breaker_user_prompt(unmapped)

    try:
        payload = _complete_mapping_json(
            client,
            model=LLM_PRIMARY_MODEL,
            user_prompt=user_prompt,
            sleep=sleep,
        )
    except Exception as primary_error:
        logger.warning(
            "GPT-4o-mini mapping tie-breaker failed after retries: %s; falling back to GPT-4o",
            primary_error,
        )
        try:
            payload = _complete_mapping_json(
                client,
                model=LLM_FALLBACK_MODEL,
                user_prompt=user_prompt,
                sleep=sleep,
            )
        except Exception as fallback_error:
            logger.error(
                "GPT-4o mapping tie-breaker also failed after retries: %s; leaving accounts unmapped",
                fallback_error,
            )
            return list(unmapped)

    return _parse_llm_mappings(unmapped, payload)


def _build_tie_breaker_user_prompt(unmapped: Sequence[MappingResult]) -> str:
    lines = [
        f"{index}. Code: {account.source_code}, Name: {account.source_name}"
        for index, account in enumerate(unmapped, start=1)
    ]
    return "Map the following accounts:\n" + "\n".join(lines)


def _complete_mapping_json(
    client: OpenAI,
    *,
    model: str,
    user_prompt: str,
    sleep: SleepFn,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(LLM_MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=LLM_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": MAPPING_TIE_BREAKER_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty LLM response content")
            payload = json.loads(content)
            if not isinstance(payload, dict) or "mappings" not in payload:
                raise ValueError("LLM response missing 'mappings' key")
            if not isinstance(payload["mappings"], list):
                raise ValueError("LLM 'mappings' value is not a list")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < LLM_MAX_ATTEMPTS - 1:
                sleep(LLM_BACKOFF_SECONDS[attempt])
    assert last_error is not None
    raise last_error


def _parse_llm_mappings(
    unmapped: Sequence[MappingResult],
    payload: dict[str, Any],
) -> list[MappingResult]:
    by_index: dict[int, dict[str, Any]] = {}
    for entry in payload["mappings"]:
        if not isinstance(entry, dict):
            continue
        raw_index = entry.get("index")
        raw_line = entry.get("canonical_line")
        if not isinstance(raw_index, int) or not isinstance(raw_line, str):
            continue
        by_index[raw_index] = entry

    results: list[MappingResult] = []
    for position, account in enumerate(unmapped, start=1):
        if position not in by_index:
            results.append(account)
            continue

        entry = by_index[position]
        canonical_line = str(entry["canonical_line"]).strip()
        confidence = _parse_llm_confidence(entry.get("confidence"))
        if canonical_line not in MAPPING_TIE_BREAKER_CANONICAL_LINES:
            results.append(account)
            continue

        if canonical_line == "unmapped":
            results.append(
                MappingResult(
                    source_code=account.source_code,
                    source_name=account.source_name,
                    canonical_line=None,
                    confidence=confidence,
                    method="llm",
                )
            )
            continue

        results.append(
            MappingResult(
                source_code=account.source_code,
                source_name=account.source_name,
                canonical_line=canonical_line,
                confidence=confidence,
                method="llm",
            )
        )
    return results


def _parse_llm_confidence(raw: object) -> Decimal | None:
    """Parse LLM self-reported confidence (0–1) to Decimal(0.01); None if missing/invalid."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return None
            value = Decimal(text)
        elif isinstance(raw, (int, float, Decimal)):
            value = Decimal(str(raw))
        else:
            return None
    except Exception:
        return None
    if value.is_nan() or value.is_infinite():
        return None
    if value < 0:
        value = Decimal("0")
    elif value > 1:
        value = Decimal("1")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)