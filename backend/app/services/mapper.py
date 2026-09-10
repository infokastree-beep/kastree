"""Hybrid account mapper — Tiers 1–4 (exact, fuzzy, code-range, LLM).

Tier 4 (LLM tie-breaker) runs only on accounts that fell through Tiers 1–3
(method=None). That includes Appendix C code-range misses and name-vs-band
contradictions (Option B): clear conflicts with the band default leave the
account for Tier 4 instead of returning a confidently wrong line. On LLM
outage after the mini→4o fallback chain, those accounts remain method=None
rather than failing the whole mapping request.
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
# Provisional: Appendix C heuristics only. Lowered from 0.65 so code_range
# suggestions read as weak priors (Option A). Name-vs-band contradictions
# fall through to Tier 4 instead of returning a wrong line (Option B).
CODE_RANGE_CONFIDENCE = Decimal("0.50")
EXACT_CONFIDENCE = Decimal("1.00")

LLM_PRIMARY_MODEL = "gpt-4o-mini"
LLM_FALLBACK_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0.1
# 1 initial attempt + 3 retries (Section 7.1: "3 retries with exponential backoff").
LLM_MAX_ATTEMPTS = 4
LLM_BACKOFF_SECONDS = (1, 2, 4)

# Appendix C ranges that resolve to exactly one canonical line.
# Range defaults are specialised by name inside _tier3_code_range where a single
# band covers multiple P&L concepts (e.g. 7000–7999 depreciation vs amortisation
# vs interest; 6000–6999 opex vs depreciation; interest income vs expense polarity).
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

    # BS contra-assets must never land on P&L depreciation/amortisation — their
    # credit balances net against the related asset leaf on the SOFP.
    contra_asset = _contra_asset_canonical_from_name(source_name)
    if contra_asset is not None:
        return MappingResult(
            source_code=source_code,
            source_name=source_name,
            canonical_line=contra_asset,
            confidence=CODE_RANGE_CONFIDENCE,
            method="code_range",
        )

    # Genuine misc current asset (e.g. VAT Recoverable) — not trade debtors,
    # not taxes_payable. No Tier 3 code-range band owns this; name cue only.
    if _other_receivables_from_name(source_name) is not None:
        return MappingResult(
            source_code=source_code,
            source_name=source_name,
            canonical_line="other_receivables",
            confidence=CODE_RANGE_CONFIDENCE,
            method="code_range",
        )

    for start, end, canonical_line in UNAMBIGUOUS_CODE_RANGES:
        if start <= code_int <= end:
            band_default = canonical_line
            resolved = band_default
            specialised = False
            # Name carve-outs where a broad range default would mis-file a clear concept.
            if start == 7000 and end == 7999 and _name_suggests_amortisation(source_name):
                resolved = "amortisation"
                specialised = True
            elif start == 6000 and end == 6999 and _name_suggests_depreciation(source_name):
                resolved = "depreciation"
                specialised = True
            else:
                interest_line = _interest_canonical_from_name(source_name)
                if interest_line is not None:
                    resolved = interest_line
                    specialised = True
            # Option B: clear name-vs-band contradiction → leave for Tier 4.
            # Do not invent an alternate line here; specialised carve-outs above win.
            if not specialised and _name_contradicts_band_default(
                band_default, source_name
            ):
                return None
            return MappingResult(
                source_code=source_code,
                source_name=source_name,
                canonical_line=resolved,
                confidence=CODE_RANGE_CONFIDENCE,
                method="code_range",
            )
    return None


def _name_contradicts_band_default(band_default: str, source_name: str) -> bool:
    """True when the account name clearly conflicts with the Appendix C band default.

    Conservative: only fall through when the name is a clear other concept.
    Ambiguous / empty names keep the band default (still at low confidence).
    """
    normalized = normalize_text(source_name)
    if not normalized:
        return False
    if band_default == "revenue":
        return _name_suggests_equity_or_dividends(normalized)
    if band_default == "cost_of_sales":
        return _name_suggests_revenue_not_cos(normalized)
    if band_default == "operating_expenses":
        return (
            _name_suggests_cost_of_sales(normalized)
            or _name_suggests_revenue_not_cos(normalized)
            or _name_suggests_equity_or_dividends(normalized)
        )
    if band_default == "depreciation":
        # Dep/amort/interest names are handled by carve-outs before this runs.
        return (
            _name_suggests_operating_expense(normalized)
            or _name_suggests_cost_of_sales(normalized)
            or _name_suggests_revenue_not_cos(normalized)
            or _name_suggests_equity_or_dividends(normalized)
        )
    return False


def _name_suggests_equity_or_dividends(normalized: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"share capital|called up share|share premium|revaluation reserve|"
            r"retained earnings|capital contribution|dividends?"
            r")\b",
            normalized,
        )
    )


def _name_suggests_cost_of_sales(normalized: str) -> bool:
    return bool(
        re.search(
            r"\b("
            r"cost of sales|purchases|materials|direct labou?r|subcontractors|"
            r"freight outward|packaging"
            r")\b",
            normalized,
        )
    )


def _name_suggests_revenue_not_cos(normalized: str) -> bool:
    """Sales/revenue-like names, excluding 'cost of sales' phrasing."""
    if re.search(r"\bcost of sales\b", normalized):
        return False
    return bool(
        re.search(
            r"\b("
            r"sales|revenue|saas|subscription|royalt(?:y|ies)|commission income|"
            r"other operating income"
            r")\b",
            normalized,
        )
    )


def _name_suggests_operating_expense(normalized: str) -> bool:
    """Clear opex names that must not stay on a depreciation band default."""
    if re.search(r"\bdepreciation\b", normalized) or re.search(r"\bamort", normalized):
        return False
    return bool(
        re.search(
            r"\b("
            r"rent|rates|wages|salar(?:y|ies)|staff|payroll|prsi|pension|training|"
            r"marketing|advertising|insurance|utilities|electricity|gas|"
            r"cleaning|security|travel|subsistence|recruitment|motor|"
            r"telephone|communications|repairs?|maintenance|"
            r"professional fees|legal|audit|tax advisory|consultancy|"
            r"bank charges?|stationery|postage|entertainment|"
            r"software licences|cloud hosting|helpdesk|bad debts?|"
            r"foreign exchange|subscriptions?|memberships?|it costs?|expenses?"
            r")\b",
            normalized,
        )
    )


def _name_suggests_amortisation(source_name: str) -> bool:
    """True when the account name clearly indicates amortisation (not depreciation)."""
    normalized = normalize_text(source_name)
    return bool(re.search(r"\bamort", normalized))


def _name_suggests_depreciation(source_name: str) -> bool:
    """True when the account name clearly indicates depreciation (not generic opex)."""
    normalized = normalize_text(source_name)
    # Accumulated / provision-for depreciation is a BS contra-asset, not a P&L charge.
    if _contra_asset_canonical_from_name(source_name) is not None:
        return False
    return bool(re.search(r"\bdepreciation\b", normalized))


def _contra_asset_canonical_from_name(source_name: str) -> str | None:
    """Map BS contra-asset accounts to the asset leaf they net against.

    Credit balances on these accounts correctly reduce the debit-normal SOFP leaf
    via existing ``_statement_amount`` netting. Returning None leaves P&L charges alone.

    Two families (same bug class — name cue must hit, or the row can be mis-filed
    onto a P&L line or left unmapped):

    1. PP&E / intangibles
       - Accumulated Depreciation / Amortisation (full)
       - Accum. / Accum / Acc. / Acc + Depreciation / Depn / Amortisation
       - A/Depreciation, A/Depn
       - Provision for Depreciation / Amortisation / Depn
    2. Trade receivables
       - Allowance / Provision for Doubtful or Bad Debts
       - Doubtful Debts (provision)
       - Allowance for Expected Credit Losses / ECL
       - Explicitly NOT bare P&L ``Bad Debt Expense`` / write-offs

    Bare P&L charges (``Depreciation``, ``Depn - Vehicles``, ``Amortisation``,
    ``Bad Debt Expense``) have no contra cue and correctly return None.
    """
    normalized = normalize_text(source_name)

    # --- Trade receivables contra (allowance / doubtful / ECL) ---
    # Exclude P&L expense / write-off wording so charges stay off the asset leaf.
    if not re.search(r"\b(expense|written off|write[- ]?offs?|charge)\b", normalized):
        if re.search(
            r"\b("
            r"allowance for (doubtful|bad|expected credit)|"
            r"provision for (doubtful|bad)|"
            r"doubtful debts?|"
            r"bad debts? (allowance|provision)|"
            r"expected credit losses?"
            r")\b",
            normalized,
        ):
            return "trade_receivables"

    # --- PP&E / intangible contra (accumulated / Acc. / A/Depn / provision-for) ---
    has_contra_cue = bool(
        re.search(r"\baccumulat", normalized)
        or re.search(r"\baccum\.?\b", normalized)
        or re.search(r"\bacc\.?\b", normalized)
        or re.search(r"\ba\s*/\s*dep", normalized)
        # No trailing \b after amort — "amortisation" must match the amort stem.
        or re.search(r"\bprovision for (depreciation|amort|depn)", normalized)
    )
    if not has_contra_cue:
        return None
    if re.search(r"\bamort", normalized):
        return "intangible_assets"
    if re.search(r"\bdepreciation\b", normalized) or re.search(r"\bdepn\b", normalized):
        return "property_plant_equipment"
    # A/Dep… cue already implies depreciation when no amort token present
    if re.search(r"\ba\s*/\s*dep", normalized):
        return "property_plant_equipment"
    return None


def _other_receivables_from_name(source_name: str) -> str | None:
    """Map clear miscellaneous receivable names to ``other_receivables``.

    VAT Recoverable / VAT receivable is the confirmed live gap: an asset owed
    *to* the entity that must not become ``taxes_payable`` or be forced into
    ``trade_receivables``. Returns None for VAT Payable / VAT control liability.
    """
    normalized = normalize_text(source_name)
    if re.search(r"\bvat\s+(recoverable|receivable)\b", normalized):
        return "other_receivables"
    if re.search(r"\binput\s+vat\b", normalized) and not re.search(
        r"\b(payable|control|liability)\b", normalized
    ):
        return "other_receivables"
    return None


def _interest_canonical_from_name(source_name: str) -> str | None:
    """Map interest-named accounts to income vs expense; None if not interest.

    Polarity: expense/paid/charge wins; otherwise income → interest_income;
    bare interest defaults to interest_expense.
    """
    normalized = normalize_text(source_name)
    if not re.search(r"\binterest\b", normalized):
        return None
    if re.search(r"\b(expense|paid|payable|charge)\b", normalized):
        return "interest_expense"
    if re.search(r"\bincome\b", normalized):
        return "interest_income"
    return "interest_expense"


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