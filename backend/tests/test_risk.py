"""Tests for MVP risk rules and RiskFlagRecord JSONB schema."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.risk import AffectedAccount, RiskFlagRecord
from app.schemas.variance import VarianceAnalysisResult, VarianceItemRecord
from app.services.risk import (
    NEGATIVE_CASH_DESCRIPTION,
    evaluate_negative_cash,
    evaluate_risks,
    evaluate_unusual_variance,
)


@dataclass(frozen=True)
class _Acct:
    account_code: str
    account_name: str
    net_balance: Decimal
    canonical_line: str


def _acct(
    code: str,
    name: str,
    *,
    net_balance: str,
    canonical_line: str,
) -> _Acct:
    return _Acct(code, name, Decimal(net_balance), canonical_line)


def _variance_item(
    code: str,
    *,
    name: str | None = None,
    current: str = "100.00",
    prior: str = "100.00",
    variance_amount: str = "0.00",
    variance_pct: str | None,
    direction: str = "increase",
    is_material: bool = True,
) -> VarianceItemRecord:
    return VarianceItemRecord(
        line_item_code=code,
        line_item_name=name or code.replace("_", " ").title(),
        current_amount=current,
        prior_amount=prior,
        variance_amount=variance_amount,
        variance_pct=variance_pct,
        direction=direction,  # type: ignore[arg-type]
        is_material=is_material,
    )


# --- Schema -----------------------------------------------------------------


def test_risk_flag_record_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RiskFlagRecord.model_validate(
            {
                "rule_name": "negative_cash",
                "severity": "warning",
                "description": "test",
                "extra_field": True,
            }
        )

    errors = exc_info.value.errors()
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("extra_field",)
        for error in errors
    )


def test_affected_account_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AffectedAccount.model_validate(
            {
                "account_code": "1000",
                "account_name": "Cash",
                "net_balance": "-50.00",
                "canonical_line": "cash",
            }
        )

    assert any(error["type"] == "extra_forbidden" for error in exc_info.value.errors())


# --- Rule 1: Negative Cash/Bank ---------------------------------------------


def test_negative_cash_flagged_with_account_details() -> None:
    accounts = [
        _acct("1000", "Cash", net_balance="-50.00", canonical_line="cash"),
        _acct("1010", "Bank", net_balance="-10.00", canonical_line="cash"),
        _acct("2000", "Payables", net_balance="-100.00", canonical_line="trade_payables"),
    ]

    flag = evaluate_negative_cash(accounts)

    assert flag is not None
    assert flag.rule_name == "negative_cash"
    assert flag.severity == "warning"
    assert flag.description == NEGATIVE_CASH_DESCRIPTION
    assert flag.recommended_action == "Verify with bank statements."
    assert flag.affected_accounts is not None
    assert len(flag.affected_accounts) == 2
    assert flag.affected_accounts[0].model_dump() == {
        "account_code": "1000",
        "account_name": "Cash",
        "net_balance": "-50.00",
    }
    assert flag.affected_accounts[1].model_dump() == {
        "account_code": "1010",
        "account_name": "Bank",
        "net_balance": "-10.00",
    }


def test_positive_cash_not_flagged() -> None:
    accounts = [
        _acct("1000", "Cash", net_balance="500.00", canonical_line="cash"),
        _acct("1010", "Bank", net_balance="0.00", canonical_line="cash"),
    ]
    assert evaluate_negative_cash(accounts) is None


# --- Rule 2: Unusual Variance (tier boundaries) -----------------------------


def test_unusual_variance_skipped_with_exactly_2_months_history() -> None:
    """< 3 months → skip entirely, even with a huge current variance."""
    item = _variance_item("revenue", name="Revenue", variance_pct="90.00")
    history = [Decimal("5.00"), Decimal("6.00")]  # exactly 2

    assert evaluate_unusual_variance(item, history) is None


def test_unusual_variance_50_pct_tier_at_exactly_3_months() -> None:
    """3–11 months: flag only when abs(pct) exceeds 50 (not >=)."""
    item_just_over = _variance_item(
        "revenue", name="Revenue", variance_pct="50.01"
    )
    item_exact = _variance_item("revenue", name="Revenue", variance_pct="50.00")
    item_under = _variance_item("revenue", name="Revenue", variance_pct="49.99")
    history = [Decimal("1.00"), Decimal("2.00"), Decimal("3.00")]  # exactly 3

    flagged = evaluate_unusual_variance(item_just_over, history)
    assert flagged is not None
    assert flagged.rule_name == "unusual_variance"
    assert flagged.severity == "warning"
    assert flagged.description == (
        "Revenue has varied by 50.01% compared to the prior period, which is "
        "unusual based on 3 months of historical data. Review for one-off "
        "transactions or data errors."
    )
    assert flagged.recommended_action == (
        "Review for one-off transactions or data errors."
    )

    assert evaluate_unusual_variance(item_exact, history) is None
    assert evaluate_unusual_variance(item_under, history) is None


def test_unusual_variance_stdev_tier_at_exactly_12_months() -> None:
    """12+ months: flag when |current − mean| > 3 × sample stdev."""
    # Eleven months near 5%, one near 5% → mean ≈ 5, small stdev.
    history = [Decimal("5.00")] * 11 + [Decimal("5.10")]
    assert len(history) == 12

    # Far from the cluster → unusual.
    outlier = _variance_item("revenue", name="Revenue", variance_pct="40.00")
    flagged = evaluate_unusual_variance(outlier, history)
    assert flagged is not None
    assert "12 months" in flagged.description
    assert "40.00%" in flagged.description

    # Inside the cluster → not unusual.
    normal = _variance_item("revenue", name="Revenue", variance_pct="5.05")
    assert evaluate_unusual_variance(normal, history) is None


def test_unusual_variance_extreme_outlier_uses_history_only_baseline() -> None:
    """Current period must not enter its own mean/stdev baseline.

    History: 12 normal months, all under 10%. Current: 500% — must be flagged.
    Also proves that folding current into the baseline dampens the z-score enough
    that a milder-but-still-real outlier (10%) would be masked (z ≤ 3) while the
    history-only baseline still detects it (z > 3).
    """
    from app.services.risk import _decimal_mean, _decimal_sample_stdev

    history = [
        Decimal("3.00"),
        Decimal("4.00"),
        Decimal("5.00"),
        Decimal("5.00"),
        Decimal("6.00"),
        Decimal("4.00"),
        Decimal("5.00"),
        Decimal("5.00"),
        Decimal("6.00"),
        Decimal("4.00"),
        Decimal("5.00"),
        Decimal("5.00"),
    ]
    assert len(history) == 12
    assert all(value < Decimal("10") for value in history)

    extreme = _variance_item("revenue", name="Revenue", variance_pct="500.00")
    assert evaluate_unusual_variance(extreme, history) is not None

    # --- Correct baseline: history only ---
    correct_mean = _decimal_mean(history)
    correct_stdev = _decimal_sample_stdev(history, correct_mean)
    correct_z_extreme = abs(Decimal("500.00") - correct_mean) / correct_stdev
    assert correct_z_extreme > Decimal("3")

    # --- Buggy baseline: current incorrectly included among the priors ---
    contaminated = list(history) + [Decimal("500.00")]
    contam_mean = _decimal_mean(contaminated)
    contam_stdev = _decimal_sample_stdev(contaminated, contam_mean)
    contam_z_extreme = abs(Decimal("500.00") - contam_mean) / contam_stdev
    # Same 500% event: z collapses from hundreds to ~3.3 when self-included.
    assert contam_z_extreme < correct_z_extreme
    assert contam_z_extreme < Decimal("4")

    # Milder outlier that history-only still catches, but self-inclusion masks:
    mild = Decimal("10.00")
    correct_z_mild = abs(mild - correct_mean) / correct_stdev
    contam_mild = list(history) + [mild]
    contam_mild_mean = _decimal_mean(contam_mild)
    contam_mild_stdev = _decimal_sample_stdev(contam_mild, contam_mild_mean)
    contam_z_mild = abs(mild - contam_mild_mean) / contam_mild_stdev
    assert correct_z_mild > Decimal("3")
    assert contam_z_mild <= Decimal("3")
    assert (
        evaluate_unusual_variance(
            _variance_item("revenue", name="Revenue", variance_pct="10.00"),
            history,
        )
        is not None
    )


def test_unusual_variance_four_monthly_observations_uses_50pct_bar() -> None:
    """3–11 bucket: typical MoM 20% is not unusual; 60% MoM is."""
    history = [Decimal("4.2"), Decimal("6.1"), Decimal("-2.0"), Decimal("8.5")]
    twenty = _variance_item("revenue", name="Revenue", variance_pct="20.00")
    sixty = _variance_item("revenue", name="Revenue", variance_pct="60.00")
    assert evaluate_unusual_variance(twenty, history) is None
    flagged = evaluate_unusual_variance(sixty, history)
    assert flagged is not None
    assert "4 months" in flagged.description


def test_unusual_variance_twelve_quiet_monthly_observations_flags_15pct_mom() -> None:
    """12+ bucket on a quiet MoM series: 15% exceeds 3σ; 8% does not."""
    history = [
        Decimal("4.2"),
        Decimal("6.1"),
        Decimal("-2.0"),
        Decimal("8.5"),
        Decimal("3.0"),
        Decimal("5.5"),
        Decimal("1.2"),
        Decimal("7.0"),
        Decimal("-1.5"),
        Decimal("4.8"),
        Decimal("6.3"),
        Decimal("2.9"),
    ]
    assert len(history) == 12
    fifteen = _variance_item("revenue", name="Revenue", variance_pct="15.00")
    eight = _variance_item("revenue", name="Revenue", variance_pct="8.00")
    flagged = evaluate_unusual_variance(fifteen, history)
    assert flagged is not None
    assert "12 months" in flagged.description
    assert evaluate_unusual_variance(eight, history) is None


def test_unusual_variance_skips_when_variance_pct_is_none() -> None:
    item = _variance_item("interest_income", variance_pct=None)
    history = [Decimal("10.00")] * 3
    assert evaluate_unusual_variance(item, history) is None


def test_evaluate_risks_combines_both_rules() -> None:
    accounts = [
        _acct("1000", "Cash", net_balance="-25.00", canonical_line="cash"),
    ]
    variance = VarianceAnalysisResult(
        items=[
            _variance_item(
                "operating_expenses",
                name="Operating expenses",
                variance_pct="60.00",
                direction="increase",
            )
        ]
    )
    history = {
        "operating_expenses": [Decimal("2.00"), Decimal("3.00"), Decimal("4.00")],
    }

    flags = evaluate_risks(
        accounts,
        variance_result=variance,
        historical_variance_pcts=history,
    )

    assert [flag.rule_name for flag in flags] == [
        "negative_cash",
        "unusual_variance",
    ]
    assert flags[0].to_jsonb()["affected_accounts"][0]["net_balance"] == "-25.00"
