"""Tests for validation_results schemas and §4.2.1 validator checks."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.trial_balance import ValidationCheck, ValidationResults
from app.services.statements import compute_net_profit
from app.services.validator import SimpleMappedAccount, validate_trial_balance


def _acct(
    code: str,
    name: str,
    *,
    debit: str = "0",
    credit: str = "0",
    canonical_line: str,
) -> SimpleMappedAccount:
    debit_d = Decimal(debit)
    credit_d = Decimal(credit)
    return SimpleMappedAccount(
        account_code=code,
        account_name=name,
        debit=debit_d,
        credit=credit_d,
        net_balance=debit_d - credit_d,
        canonical_line=canonical_line,
    )


def _by_name(results: ValidationResults, check_name: str) -> ValidationCheck:
    matches = [check for check in results.checks if check.check_name == check_name]
    assert len(matches) == 1, f"expected one {check_name}, got {len(matches)}"
    return matches[0]


# --- Schema tests (existing) -------------------------------------------------


def test_validation_results_serializes_check_name_key() -> None:
    results = ValidationResults(
        checks=[
            ValidationCheck(
                check_name="tb_integrity",
                passed=False,
                severity="error",
                message=(
                    "Total debits (125,000.00) do not equal total credits (125,050.00). "
                    "Difference: 50.00"
                ),
                details={
                    "total_debits": "125000.00",
                    "total_credits": "125050.00",
                    "difference": "50.00",
                },
            ),
            ValidationCheck(
                check_name="balance_sheet_balance",
                passed=True,
                severity="error",
                message="Balance sheet balances within tolerance.",
            ),
        ]
    )

    payload = results.to_jsonb()

    assert payload == {
        "checks": [
            {
                "check_name": "tb_integrity",
                "passed": False,
                "severity": "error",
                "message": (
                    "Total debits (125,000.00) do not equal total credits (125,050.00). "
                    "Difference: 50.00"
                ),
                "details": {
                    "total_debits": "125000.00",
                    "total_credits": "125050.00",
                    "difference": "50.00",
                },
            },
            {
                "check_name": "balance_sheet_balance",
                "passed": True,
                "severity": "error",
                "message": "Balance sheet balances within tolerance.",
            },
        ]
    }


def test_validation_check_details_defaults_to_none_when_omitted() -> None:
    check = ValidationCheck(
        check_name="tb_integrity",
        passed=True,
        severity="error",
        message="Trial balance debits equal credits.",
    )

    assert check.details is None
    assert ValidationResults(checks=[check]).to_jsonb() == {
        "checks": [
            {
                "check_name": "tb_integrity",
                "passed": True,
                "severity": "error",
                "message": "Trial balance debits equal credits.",
            }
        ]
    }


def test_validation_check_rejects_wrong_key_name() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ValidationCheck.model_validate(
            {
                "name": "tb_integrity",
                "passed": True,
                "severity": "error",
                "message": "Trial balance debits equal credits.",
            }
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("check_name",) for error in errors)
    assert any(error["type"] == "extra_forbidden" and error["loc"] == ("name",) for error in errors)


def test_validation_results_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ValidationResults.model_validate(
            {
                "checks": [],
                "summary": "all good",
            }
        )


# --- Validator checks --------------------------------------------------------


def test_tb_integrity_passes() -> None:
    accounts = [
        _acct("1000", "Cash", debit="10000.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="10000.00", canonical_line="revenue"),
    ]
    results = validate_trial_balance(accounts)
    check = _by_name(results, "tb_integrity")
    assert check.passed is True
    assert check.severity == "error"
    assert check.details is None


def test_tb_integrity_fails_with_section_10_3_details_shape() -> None:
    accounts = [
        _acct("1000", "Cash", debit="125000.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="125050.00", canonical_line="revenue"),
    ]
    results = validate_trial_balance(accounts)
    check = _by_name(results, "tb_integrity")
    assert check.passed is False
    assert check.severity == "error"
    assert check.details == {
        "total_debits": "125000.00",
        "total_credits": "125050.00",
        "difference": "50.00",
    }
    assert "125,000.00" in check.message
    assert "Difference: 50.00" in check.message


def test_balance_sheet_balance_passes() -> None:
    accounts = [
        _acct("1000", "Cash", debit="10000.00", canonical_line="cash"),
        _acct("2000", "Payables", credit="4000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="6000.00", canonical_line="share_capital"),
    ]
    check = _by_name(validate_trial_balance(accounts), "balance_sheet_balance")
    assert check.passed is True
    assert check.message == "Balance sheet balances within tolerance."


def test_balance_sheet_balance_fails() -> None:
    """Assets exceed SC + opening RE + profit — no P&L line explains the gap."""
    accounts = [
        _acct("1000", "Cash", debit="11000.00", canonical_line="cash"),
        _acct("2000", "Payables", credit="4000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="5000.00", canonical_line="share_capital"),
        _acct("9999", "Suspense", credit="2000.00", canonical_line="unmapped"),
    ]
    check = _by_name(validate_trial_balance(accounts), "balance_sheet_balance")
    assert check.passed is False
    assert check.details is not None
    assert check.details["difference"] == "2000.00"


def test_balance_sheet_balance_passes_with_open_pnl_and_zero_dividends() -> None:
    """False-positive regression: open P&L must not fail balance_sheet_balance.

    Same fixture as test_net_assets_passes_with_open_pnl_and_zero_dividends.
    Revenue 5_000 − CoS 2_000 − opex 1_000 = profit 2_000.
    Assets 12_000 == payables 3_000 + SC 5_000 + opening RE 2_000 + profit 2_000.
    """
    accounts = [
        _acct("1000", "Cash", debit="12000.00", canonical_line="cash"),
        _acct("2000", "Payables", credit="3000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="5000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="2000.00", canonical_line="retained_earnings"),
        _acct("4000", "Revenue", credit="5000.00", canonical_line="revenue"),
        _acct("5000", "Cost of sales", debit="2000.00", canonical_line="cost_of_sales"),
        _acct("6000", "Operating expenses", debit="1000.00", canonical_line="operating_expenses"),
    ]
    results = validate_trial_balance(accounts)
    balance_sheet = _by_name(results, "balance_sheet_balance")
    assert balance_sheet.passed is True
    assert balance_sheet.details is None
    assert _by_name(results, "net_assets").passed is True


def test_retained_earnings_rollforward_passes() -> None:
    prior = [
        _acct("3100", "Retained earnings", credit="5000.00", canonical_line="retained_earnings"),
        _acct("1000", "Cash", debit="5000.00", canonical_line="cash"),
    ]
    current = [
        _acct("3100", "Retained earnings", credit="8000.00", canonical_line="retained_earnings"),
        _acct("1000", "Cash", debit="11000.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="3000.00", canonical_line="revenue"),
    ]
    check = _by_name(
        validate_trial_balance(current, prior_accounts=prior),
        "retained_earnings_rollforward",
    )
    assert check.passed is True
    assert check.severity == "warning"


def test_retained_earnings_rollforward_fails() -> None:
    prior = [
        _acct("3100", "Retained earnings", credit="5000.00", canonical_line="retained_earnings"),
        _acct("1000", "Cash", debit="5000.00", canonical_line="cash"),
    ]
    current = [
        _acct("3100", "Retained earnings", credit="7000.00", canonical_line="retained_earnings"),
        _acct("1000", "Cash", debit="10000.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="3000.00", canonical_line="revenue"),
    ]
    # Expected RE = 5000 + 3000 = 8000, actual closing RE = 7000
    check = _by_name(
        validate_trial_balance(current, prior_accounts=prior),
        "retained_earnings_rollforward",
    )
    assert check.passed is False
    assert check.severity == "warning"
    assert check.details is not None
    assert check.details["difference"] == "1000.00"


def test_retained_earnings_rollforward_passes_with_realistic_pnl() -> None:
    """Check 3 pass: prior RE + multi-line P&L profit = current RE.

    Revenue 10_000 − CoS 4_000 − opex 2_500 − depreciation 500 + interest
    income 200 − interest expense 100 − tax 300 = profit 2_800.
    Prior closing RE 5_000 + 2_800 = expected current RE 7_800.
    """
    prior = [
        _acct("1000", "Cash", debit="8000.00", canonical_line="cash"),
        _acct("3000", "Share capital", credit="3000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="5000.00", canonical_line="retained_earnings"),
    ]
    current = [
        _acct("1000", "Cash", debit="13600.00", canonical_line="cash"),
        _acct("3000", "Share capital", credit="3000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="7800.00", canonical_line="retained_earnings"),
        _acct("4000", "Revenue", credit="10000.00", canonical_line="revenue"),
        _acct("5000", "Cost of sales", debit="4000.00", canonical_line="cost_of_sales"),
        _acct("6000", "Operating expenses", debit="2500.00", canonical_line="operating_expenses"),
        _acct("7000", "Depreciation", debit="500.00", canonical_line="depreciation"),
        _acct("8000", "Interest income", credit="200.00", canonical_line="interest_income"),
        _acct("8100", "Interest expense", debit="100.00", canonical_line="interest_expense"),
        _acct("8200", "Tax", debit="300.00", canonical_line="tax"),
    ]
    profit = compute_net_profit(current)
    assert profit == Decimal("2800.00")

    check = _by_name(
        validate_trial_balance(current, prior_accounts=prior),
        "retained_earnings_rollforward",
    )
    assert check.passed is True
    assert check.severity == "warning"
    assert check.details is None


def test_retained_earnings_rollforward_fails_with_realistic_pnl() -> None:
    """Check 3 fail: same multi-line P&L but current RE short by 500."""
    prior = [
        _acct("1000", "Cash", debit="8000.00", canonical_line="cash"),
        _acct("3000", "Share capital", credit="3000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="5000.00", canonical_line="retained_earnings"),
    ]
    current = [
        _acct("1000", "Cash", debit="13100.00", canonical_line="cash"),
        _acct("3000", "Share capital", credit="3000.00", canonical_line="share_capital"),
        # 7_300 vs expected 5_000 + 2_800 = 7_800
        _acct("3100", "Retained earnings", credit="7300.00", canonical_line="retained_earnings"),
        _acct("4000", "Revenue", credit="10000.00", canonical_line="revenue"),
        _acct("5000", "Cost of sales", debit="4000.00", canonical_line="cost_of_sales"),
        _acct("6000", "Operating expenses", debit="2500.00", canonical_line="operating_expenses"),
        _acct("7000", "Depreciation", debit="500.00", canonical_line="depreciation"),
        _acct("8000", "Interest income", credit="200.00", canonical_line="interest_income"),
        _acct("8100", "Interest expense", debit="100.00", canonical_line="interest_expense"),
        _acct("8200", "Tax", debit="300.00", canonical_line="tax"),
    ]
    assert compute_net_profit(current) == Decimal("2800.00")

    check = _by_name(
        validate_trial_balance(current, prior_accounts=prior),
        "retained_earnings_rollforward",
    )
    assert check.passed is False
    assert check.severity == "warning"
    assert check.details == {
        "closing_re_prior": "5000.00",
        "current_profit": "2800.00",
        "expected_closing_re": "7800.00",
        "closing_re_current": "7300.00",
        "difference": "500.00",
    }


def test_retained_earnings_omitted_when_no_prior_period() -> None:
    accounts = [
        _acct("1000", "Cash", debit="100.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="100.00", canonical_line="revenue"),
    ]
    results = validate_trial_balance(accounts, prior_accounts=None)
    assert all(check.check_name != "retained_earnings_rollforward" for check in results.checks)
    assert _by_name(results, "comparatives_available").passed is False


def test_net_assets_passes() -> None:
    accounts = [
        _acct("1000", "Cash", debit="10000.00", canonical_line="cash"),
        _acct("2000", "Payables", credit="3000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="4000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="3000.00", canonical_line="retained_earnings"),
    ]
    check = _by_name(validate_trial_balance(accounts), "net_assets")
    assert check.passed is True


def test_net_assets_passes_with_open_pnl_and_zero_dividends() -> None:
    """False-positive regression: open P&L must not fail net_assets.

    Assets already include the cash effect of this period's profit; opening RE
    on the TB does not. Equity for Check 4 is SC + opening RE + period profit.
    Revenue 5_000 − CoS 2_000 − opex 1_000 = profit 2_000.
    Net assets 9_000 == SC 5_000 + RE 2_000 + profit 2_000.
    """
    accounts = [
        _acct("1000", "Cash", debit="12000.00", canonical_line="cash"),
        _acct("2000", "Payables", credit="3000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="5000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="2000.00", canonical_line="retained_earnings"),
        _acct("4000", "Revenue", credit="5000.00", canonical_line="revenue"),
        _acct("5000", "Cost of sales", debit="2000.00", canonical_line="cost_of_sales"),
        _acct("6000", "Operating expenses", debit="1000.00", canonical_line="operating_expenses"),
    ]
    results = validate_trial_balance(accounts)
    net_assets = _by_name(results, "net_assets")
    assert net_assets.passed is True
    assert net_assets.details is None


def test_net_assets_fails() -> None:
    """Unmapped credit leaves SC + opening RE + profit short of net assets."""
    accounts = [
        _acct("1000", "Cash", debit="10000.00", canonical_line="cash"),
        _acct("2000", "Payables", credit="3000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="5000.00", canonical_line="share_capital"),
        # 2_000 parked in unmapped — excluded from Check 4 equity.
        _acct("9999", "Suspense", credit="2000.00", canonical_line="unmapped"),
    ]
    check = _by_name(validate_trial_balance(accounts), "net_assets")
    assert check.passed is False
    assert check.details is not None
    assert check.details["net_assets"] == "7000.00"
    assert check.details["total_equity"] == "5000.00"
    assert check.details["difference"] == "2000.00"


def test_negative_cash_passes() -> None:
    accounts = [
        _acct("1000", "Cash", debit="500.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="500.00", canonical_line="revenue"),
    ]
    check = _by_name(validate_trial_balance(accounts), "negative_cash")
    assert check.passed is True
    assert check.severity == "warning"


def test_negative_cash_fails_with_account_details() -> None:
    accounts = [
        _acct("1000", "Cash", credit="50.00", canonical_line="cash"),
        _acct("1010", "Bank", credit="10.00", canonical_line="cash"),
        _acct("2000", "Payables", debit="60.00", canonical_line="trade_payables"),
    ]
    check = _by_name(validate_trial_balance(accounts), "negative_cash")
    assert check.passed is False
    assert check.severity == "warning"
    assert check.details is not None
    assert "1000 Cash (-50.00)" in check.details["accounts"]
    assert "1010 Bank (-10.00)" in check.details["accounts"]


def test_comparatives_available_true_and_false() -> None:
    accounts = [
        _acct("1000", "Cash", debit="1.00", canonical_line="cash"),
        _acct("4000", "Sales", credit="1.00", canonical_line="revenue"),
    ]
    without = validate_trial_balance(accounts)
    assert _by_name(without, "comparatives_available").passed is False
    assert _by_name(without, "comparatives_available").severity == "info"

    with_prior = validate_trial_balance(accounts, prior_accounts=accounts)
    assert _by_name(with_prior, "comparatives_available").passed is True


def test_balance_sheet_passes_but_net_assets_fails_with_dividends_on_tb() -> None:
    """Trigger-critical fixture: BS equation holds, net_assets fails on open dividends.

    Zero P&L → period profit = 0. Check 4 equity = SC 5_000 + opening RE 3_000
    + profit 0 = 8_000 (dividends still excluded). Net assets = 7_000 after the
    cash dividend. Difference = 1_000 = open Dividends. Check 2 still passes
    because it nets Dividends as contra-equity.
    """
    accounts = [
        _acct("1000", "Cash", debit="10000.00", canonical_line="cash"),
        _acct("2000", "Trade payables", credit="3000.00", canonical_line="trade_payables"),
        _acct("3000", "Share capital", credit="5000.00", canonical_line="share_capital"),
        _acct("3100", "Retained earnings", credit="3000.00", canonical_line="retained_earnings"),
        _acct("3200", "Dividends", debit="1000.00", canonical_line="dividends"),
    ]

    results = validate_trial_balance(accounts)
    integrity = _by_name(results, "tb_integrity")
    balance_sheet = _by_name(results, "balance_sheet_balance")
    net_assets = _by_name(results, "net_assets")

    assert integrity.passed is True
    assert balance_sheet.passed is True
    assert net_assets.passed is False
    assert net_assets.severity == "error"
    assert net_assets.details == {
        "net_assets": "7000.00",
        "total_equity": "8000.00",
        "difference": "1000.00",
    }
    # Both structural checks are present independently (no short-circuit).
    assert [c.check_name for c in results.checks].count("balance_sheet_balance") == 1
    assert [c.check_name for c in results.checks].count("net_assets") == 1
    # Ready for trial_balances.validation_results JSONB + DB trigger.
    payload = results.to_jsonb()
    assert isinstance(payload["checks"], list)
    assert any(
        item["check_name"] == "net_assets" and item["passed"] is False
        for item in payload["checks"]
    )
