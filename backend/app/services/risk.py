"""MVP risk rules — Negative Cash/Bank and Unusual Variance (Product Spec §4.3, Appendix D).

Rule 2 does not fetch history itself: callers pass historical variance percentages
per line item. Tier selection is driven by len(history) only.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Protocol, Sequence

from app.schemas.risk import AffectedAccount, RiskFlagRecord
from app.schemas.variance import VarianceAnalysisResult, VarianceItemRecord

NEGATIVE_CASH_RULE = "negative_cash"
UNUSUAL_VARIANCE_RULE = "unusual_variance"

NEGATIVE_CASH_DESCRIPTION = (
    "A cash or bank account shows a negative balance. This may indicate an "
    "overdraft, uncleared items, or a data entry error. Verify with bank statements."
)
NEGATIVE_CASH_ACTION = "Verify with bank statements."

UNUSUAL_VARIANCE_ACTION = "Review for one-off transactions or data errors."
UNUSUAL_VARIANCE_TEMPLATE = (
    "{line_item} has varied by {pct}% compared to the prior period, which is "
    "unusual based on {months} months of historical data. Review for one-off "
    "transactions or data errors."
)

# Section 4.3 tier thresholds.
_MIN_MONTHS_FOR_VARIANCE_RULE = 3
_STDEV_TIER_MONTHS = 12
_STDEV_MULTIPLIER = Decimal("3")
_FALLBACK_PCT_THRESHOLD = Decimal("50")


class RiskAccount(Protocol):
    """Mapped TB account shape for Rule 1."""

    account_code: str
    account_name: str
    net_balance: Decimal
    canonical_line: str


def evaluate_risks(
    accounts: Sequence[RiskAccount],
    *,
    variance_result: VarianceAnalysisResult | None = None,
    historical_variance_pcts: Mapping[str, Sequence[Decimal]] | None = None,
) -> list[RiskFlagRecord]:
    """Run MVP risk rules. Returns zero or more RiskFlagRecord instances."""
    flags: list[RiskFlagRecord] = []
    cash_flag = evaluate_negative_cash(accounts)
    if cash_flag is not None:
        flags.append(cash_flag)

    if variance_result is not None:
        history_by_code = historical_variance_pcts or {}
        for item in variance_result.items:
            flag = evaluate_unusual_variance(
                item,
                history_by_code.get(item.line_item_code, ()),
            )
            if flag is not None:
                flags.append(flag)

    return flags


def evaluate_negative_cash(accounts: Sequence[RiskAccount]) -> RiskFlagRecord | None:
    """Rule 1: flag when any cash-mapped account has net_balance < 0."""
    negatives = [
        account
        for account in accounts
        if account.canonical_line == "cash" and account.net_balance < Decimal("0")
    ]
    if not negatives:
        return None

    affected = [
        AffectedAccount(
            account_code=account.account_code,
            account_name=account.account_name,
            net_balance=_money_str(account.net_balance),
        )
        for account in negatives
    ]
    return RiskFlagRecord(
        rule_name=NEGATIVE_CASH_RULE,
        severity="warning",
        description=NEGATIVE_CASH_DESCRIPTION,
        affected_accounts=affected,
        recommended_action=NEGATIVE_CASH_ACTION,
    )


def evaluate_unusual_variance(
    item: VarianceItemRecord,
    historical_variance_pcts: Sequence[Decimal],
) -> RiskFlagRecord | None:
    """Rule 2: tiered unusual-variance check using caller-supplied history.

    - len < 3: skip (return None)
    - 3–11: flag when abs(current variance_pct) > 50
    - 12+: flag when abs(current − 12-month mean) > 3 × sample stdev
      (uses the most recent 12 historical percentages)
    """
    history_len = len(historical_variance_pcts)
    if history_len < _MIN_MONTHS_FOR_VARIANCE_RULE:
        return None
    if item.variance_pct is None:
        return None

    current_pct = Decimal(item.variance_pct)

    if history_len >= _STDEV_TIER_MONTHS:
        # Baseline is built ONLY from prior periods — never include the current
        # period's variance_pct in the mean/stdev window. Including it would pull
        # the mean toward the outlier and inflate stdev, dampening its own z-score.
        window = list(historical_variance_pcts[-_STDEV_TIER_MONTHS:])
        months = _STDEV_TIER_MONTHS
        if not _exceeds_stdev_threshold(current_pct, window):
            return None
    else:
        months = history_len
        if abs(current_pct) <= _FALLBACK_PCT_THRESHOLD:
            return None

    pct_display = _pct_str(abs(current_pct))
    description = UNUSUAL_VARIANCE_TEMPLATE.format(
        line_item=item.line_item_name,
        pct=pct_display,
        months=months,
    )
    return RiskFlagRecord(
        rule_name=UNUSUAL_VARIANCE_RULE,
        severity="warning",
        description=description,
        affected_accounts=None,
        recommended_action=UNUSUAL_VARIANCE_ACTION,
    )


def _exceeds_stdev_threshold(
    current_pct: Decimal,
    window: Sequence[Decimal],
) -> bool:
    """True when |current − mean| > 3 × sample standard deviation.

    *window* must be historical percentages only — the current period is compared
    against this baseline and must not appear inside it.
    """
    mean = _decimal_mean(window)
    stdev = _decimal_sample_stdev(window, mean)
    deviation = abs(current_pct - mean)
    if stdev == Decimal("0"):
        return deviation > Decimal("0")
    return deviation > _STDEV_MULTIPLIER * stdev


def _decimal_mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values))


def _decimal_sample_stdev(values: Sequence[Decimal], mean: Decimal) -> Decimal:
    """Sample standard deviation (divide by n−1), not population (n).

    Documented choice: the Product Spec does not specify sample vs population.
    Sample stdev is used because the 12 historical months are treated as a
    sample of the client's variance distribution, not the full population of
    all possible periods. Requires at least two observations.
    """
    n = len(values)
    if n < 2:
        return Decimal("0")
    squared = sum(((value - mean) ** 2 for value in values), Decimal("0"))
    variance = squared / Decimal(n - 1)
    return variance.sqrt()


def _money_str(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01'))}"


def _pct_str(pct: Decimal) -> str:
    return f"{pct.quantize(Decimal('0.01'))}"
