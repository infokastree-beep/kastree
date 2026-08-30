"""Deterministic trial-balance validation checks (Product Spec §4.2.1).

Returns a complete ValidationResults for every call — never raises to block
statement generation. The caller decides blocking from error-severity failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

from app.schemas.trial_balance import ValidationCheck, ValidationResults
from app.services.statements import compute_net_profit

TOLERANCE = Decimal("0.01")

ASSET_LINES: frozenset[str] = frozenset(
    {
        "property_plant_equipment",
        "intangible_assets",
        "inventory",
        "trade_receivables",
        "cash",
    }
)
LIABILITY_LINES: frozenset[str] = frozenset(
    {
        "trade_payables",
        "accruals",
        "loans",
    }
)
# Full equity side of A = L + E (includes dividends debit reducing equity).
EQUITY_LINES_BALANCE_SHEET: frozenset[str] = frozenset(
    {
        "share_capital",
        "retained_earnings",
        "dividends",
    }
)
# SOFP "total equity" for the net-assets cross-check starts from capital + opening
# RE, then adds current-period profit (P&L still open on the TB). Dividends stay
# excluded so this check remains independent of balance_sheet_balance — open
# Dividends still fail net_assets by exactly the dividend amount.
EQUITY_LINES_SOFP: frozenset[str] = frozenset(
    {
        "share_capital",
        "retained_earnings",
    }
)


class MappedAccount(Protocol):
    """TB row with a canonical_line assigned by the mapper."""

    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    net_balance: Decimal
    canonical_line: str


@dataclass(frozen=True)
class SimpleMappedAccount:
    """Concrete mapped account for tests and callers without TBRow."""

    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    net_balance: Decimal
    canonical_line: str


def decimal_eq(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCE


def validate_trial_balance(
    accounts: Sequence[MappedAccount],
    *,
    prior_accounts: Sequence[MappedAccount] | None = None,
) -> ValidationResults:
    """Run all §4.2.1 checks. Always returns a full ValidationResults."""
    checks: list[ValidationCheck] = [
        _check_tb_integrity(accounts),
        _check_balance_sheet_balance(accounts),
    ]
    if prior_accounts is not None:
        checks.append(_check_retained_earnings_rollforward(accounts, prior_accounts))
    checks.extend(
        [
            _check_net_assets(accounts),
            _check_negative_cash(accounts),
            _check_comparatives_available(prior_accounts is not None),
        ]
    )
    return ValidationResults(checks=checks)


class Validator:
    """Thin class wrapper matching .cursorrules Section 11.4 examples."""

    def validate(
        self,
        accounts: Sequence[MappedAccount],
        *,
        prior_accounts: Sequence[MappedAccount] | None = None,
        mapped: Sequence[MappedAccount] | None = None,
    ) -> ValidationResults:
        # `mapped` accepted as an alias for accounts (cursorrules example shape).
        rows = mapped if mapped is not None else accounts
        return validate_trial_balance(rows, prior_accounts=prior_accounts)


def _money_str(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01'))}"


def _money_display(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01')):,}"


def _sum_debits(accounts: Sequence[MappedAccount]) -> Decimal:
    return sum((account.debit for account in accounts), Decimal("0"))


def _sum_credits(accounts: Sequence[MappedAccount]) -> Decimal:
    return sum((account.credit for account in accounts), Decimal("0"))


def _total_assets(accounts: Sequence[MappedAccount]) -> Decimal:
    return sum(
        (account.net_balance for account in accounts if account.canonical_line in ASSET_LINES),
        Decimal("0"),
    )


def _credit_normal_total(accounts: Sequence[MappedAccount], lines: frozenset[str]) -> Decimal:
    """Sum credit-normal lines as positive amounts (-net_balance)."""
    return sum(
        (-account.net_balance for account in accounts if account.canonical_line in lines),
        Decimal("0"),
    )


def _total_liabilities(accounts: Sequence[MappedAccount]) -> Decimal:
    return _credit_normal_total(accounts, LIABILITY_LINES)


def _total_equity_balance_sheet(accounts: Sequence[MappedAccount]) -> Decimal:
    return _credit_normal_total(accounts, EQUITY_LINES_BALANCE_SHEET)


def _total_equity_sofp(accounts: Sequence[MappedAccount]) -> Decimal:
    """Closing equity for Check 4: SC + opening RE + period profit.

    Dividends are deliberately omitted (Product Spec §4.2.1 Check 4) so an open
    Dividends balance fails this check while balance_sheet_balance may still pass.
    Period profit must be included: SOFP-mapped assets already reflect trading
    cash/working-capital effects, but opening RE on an unclosed TB does not.
    """
    return (
        _credit_normal_total(accounts, EQUITY_LINES_SOFP)
        + compute_net_profit(accounts)
    )


def _closing_retained_earnings(accounts: Sequence[MappedAccount]) -> Decimal:
    return _credit_normal_total(accounts, frozenset({"retained_earnings"}))


def _check_tb_integrity(accounts: Sequence[MappedAccount]) -> ValidationCheck:
    total_debits = _sum_debits(accounts)
    total_credits = _sum_credits(accounts)
    difference = abs(total_debits - total_credits)
    passed = decimal_eq(total_debits, total_credits)
    if passed:
        return ValidationCheck(
            check_name="tb_integrity",
            passed=True,
            severity="error",
            message="Trial balance debits equal credits within tolerance.",
        )
    return ValidationCheck(
        check_name="tb_integrity",
        passed=False,
        severity="error",
        message=(
            f"Total debits ({_money_display(total_debits)}) do not equal "
            f"total credits ({_money_display(total_credits)}). "
            f"Difference: {_money_display(difference)}"
        ),
        details={
            "total_debits": _money_str(total_debits),
            "total_credits": _money_str(total_credits),
            "difference": _money_str(difference),
        },
    )


def _check_balance_sheet_balance(accounts: Sequence[MappedAccount]) -> ValidationCheck:
    assets = _total_assets(accounts)
    liabilities = _total_liabilities(accounts)
    equity = _total_equity_balance_sheet(accounts)
    right_hand_side = liabilities + equity
    difference = abs(assets - right_hand_side)
    passed = decimal_eq(assets, right_hand_side)
    if passed:
        return ValidationCheck(
            check_name="balance_sheet_balance",
            passed=True,
            severity="error",
            message="Balance sheet balances within tolerance.",
        )
    return ValidationCheck(
        check_name="balance_sheet_balance",
        passed=False,
        severity="error",
        message=(
            f"Total assets ({_money_display(assets)}) do not equal "
            f"total liabilities + equity ({_money_display(right_hand_side)}). "
            f"Difference: {_money_display(difference)}"
        ),
        details={
            "total_assets": _money_str(assets),
            "total_liabilities": _money_str(liabilities),
            "total_equity": _money_str(equity),
            "difference": _money_str(difference),
        },
    )


def _check_retained_earnings_rollforward(
    accounts: Sequence[MappedAccount],
    prior_accounts: Sequence[MappedAccount],
) -> ValidationCheck:
    """Check 3: prior closing RE + current-period profit = current closing RE.

    Current-period profit is :func:`compute_net_profit` — the same function as
    SOPL net_profit, SOCIE profit_for_period, and Check 4.
    """
    closing_re_prior = _closing_retained_earnings(prior_accounts)
    current_profit = compute_net_profit(accounts)
    closing_re_current = _closing_retained_earnings(accounts)
    expected = closing_re_prior + current_profit
    difference = abs(expected - closing_re_current)
    passed = decimal_eq(expected, closing_re_current)
    if passed:
        return ValidationCheck(
            check_name="retained_earnings_rollforward",
            passed=True,
            severity="warning",
            message="Retained earnings roll-forward within tolerance.",
        )
    return ValidationCheck(
        check_name="retained_earnings_rollforward",
        passed=False,
        severity="warning",
        message=(
            f"Closing RE prior ({_money_display(closing_re_prior)}) + "
            f"current profit ({_money_display(current_profit)}) = "
            f"{_money_display(expected)}, but closing RE current is "
            f"{_money_display(closing_re_current)}. "
            f"Difference: {_money_display(difference)}"
        ),
        details={
            "closing_re_prior": _money_str(closing_re_prior),
            "current_profit": _money_str(current_profit),
            "expected_closing_re": _money_str(expected),
            "closing_re_current": _money_str(closing_re_current),
            "difference": _money_str(difference),
        },
    )


def _check_net_assets(accounts: Sequence[MappedAccount]) -> ValidationCheck:
    # Check 4 compares net assets (A − L) to closing equity constructed as
    # share_capital + opening retained_earnings + current_period_profit.
    # Opening RE is the TB retained_earnings balance (profit still sits in open
    # P&L accounts). Profit uses statements.compute_net_profit — the same
    # function as SOPL net_profit / SOCIE profit_for_period.
    #
    # Dividends are still excluded from this equity figure (unlike SOCIE's
    # retained_earnings_closing = opening + profit − dividends). That keeps
    # Check 4 independent of Check 2: a balanced TB with open Dividends passes
    # balance_sheet_balance but fails net_assets by exactly the dividend amount.
    # Do not fold dividends into this total without re-reading Product Spec
    # §4.2.1 and the DB trigger that keys off this check.
    assets = _total_assets(accounts)
    liabilities = _total_liabilities(accounts)
    net_assets = assets - liabilities
    total_equity = _total_equity_sofp(accounts)
    difference = abs(net_assets - total_equity)
    passed = decimal_eq(net_assets, total_equity)
    if passed:
        return ValidationCheck(
            check_name="net_assets",
            passed=True,
            severity="error",
            message="Net assets equal total equity within tolerance.",
        )
    return ValidationCheck(
        check_name="net_assets",
        passed=False,
        severity="error",
        message=(
            f"Net assets ({_money_display(net_assets)}) do not equal "
            f"total equity ({_money_display(total_equity)}). "
            f"Difference: {_money_display(difference)}"
        ),
        details={
            "net_assets": _money_str(net_assets),
            "total_equity": _money_str(total_equity),
            "difference": _money_str(difference),
        },
    )


def _check_negative_cash(accounts: Sequence[MappedAccount]) -> ValidationCheck:
    negatives = [
        account
        for account in accounts
        if account.canonical_line == "cash" and account.net_balance < Decimal("0")
    ]
    if not negatives:
        return ValidationCheck(
            check_name="negative_cash",
            passed=True,
            severity="warning",
            message="No cash or bank accounts have a negative balance.",
        )
    detail_parts = [
        f"{account.account_code} {account.account_name} ({_money_str(account.net_balance)})"
        for account in negatives
    ]
    return ValidationCheck(
        check_name="negative_cash",
        passed=False,
        severity="warning",
        message=(
            f"{len(negatives)} cash/bank account(s) have a negative balance. "
            "Verify overdrafts or data entry errors."
        ),
        details={"accounts": "; ".join(detail_parts)},
    )


def _check_comparatives_available(has_prior_period: bool) -> ValidationCheck:
    if has_prior_period:
        return ValidationCheck(
            check_name="comparatives_available",
            passed=True,
            severity="info",
            message="Prior period trial balance is available for variance analysis.",
        )
    return ValidationCheck(
        check_name="comparatives_available",
        passed=False,
        severity="info",
        message="No prior period trial balance provided. Variance analysis disabled.",
    )
