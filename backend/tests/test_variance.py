"""Tests for period-on-period variance analysis and variance JSONB schemas."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.variance import VarianceAnalysisResult, VarianceItemRecord
from app.services.variance import compute_variance, is_material


@dataclass(frozen=True)
class _Line:
    line_item_code: str
    line_item_name: str
    amount: Decimal
    is_subtotal: bool = False


def _line(
    code: str,
    amount: str,
    *,
    name: str | None = None,
    is_subtotal: bool = False,
) -> _Line:
    return _Line(
        line_item_code=code,
        line_item_name=name or code.replace("_", " ").title(),
        amount=Decimal(amount),
        is_subtotal=is_subtotal,
    )


def _by_code(result: VarianceAnalysisResult, code: str) -> VarianceItemRecord:
    matches = [item for item in result.items if item.line_item_code == code]
    assert len(matches) == 1, f"expected one {code}, got {len(matches)}"
    return matches[0]


DEFAULT_PCT = Decimal("10.00")
DEFAULT_ABS = Decimal("1000.00")


# --- Schema tests (ValidationCheck / ValidationResults pattern) --------------


def test_variance_item_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VarianceItemRecord.model_validate(
            {
                "line_item_code": "revenue",
                "line_item_name": "Revenue",
                "current_amount": "100.00",
                "prior_amount": "90.00",
                "variance_amount": "10.00",
                "variance_pct": "11.11",
                "direction": "increase",
                "is_material": True,
                "commentary": {"text": "should not be here"},
            }
        )

    errors = exc_info.value.errors()
    assert any(
        error["type"] == "extra_forbidden" and error["loc"] == ("commentary",)
        for error in errors
    )


def test_variance_item_rejects_wrong_key_name() -> None:
    with pytest.raises(ValidationError) as exc_info:
        VarianceItemRecord.model_validate(
            {
                "code": "revenue",
                "line_item_name": "Revenue",
                "current_amount": "100.00",
                "prior_amount": "90.00",
                "variance_amount": "10.00",
                "variance_pct": "11.11",
                "direction": "increase",
                "is_material": True,
            }
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("line_item_code",) for error in errors)
    assert any(error["type"] == "extra_forbidden" and error["loc"] == ("code",) for error in errors)


def test_variance_analysis_result_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        VarianceAnalysisResult.model_validate(
            {
                "items": [],
                "summary": "all good",
            }
        )


def test_variance_analysis_result_to_jsonb_excludes_none_pct() -> None:
    result = VarianceAnalysisResult(
        items=[
            VarianceItemRecord(
                line_item_code="interest_income",
                line_item_name="Interest income",
                current_amount="250.00",
                prior_amount="0.00",
                variance_amount="250.00",
                variance_pct=None,
                direction="increase",
                is_material=False,
            )
        ]
    )

    payload = result.to_jsonb()

    assert payload == {
        "items": [
            {
                "line_item_code": "interest_income",
                "line_item_name": "Interest income",
                "current_amount": "250.00",
                "prior_amount": "0.00",
                "variance_amount": "250.00",
                "direction": "increase",
                "is_material": False,
            }
        ]
    }
    assert "variance_pct" not in payload["items"][0]
    assert "commentary" not in payload["items"][0]


# --- Service tests -----------------------------------------------------------


def test_is_material_matches_appendix_b() -> None:
    assert is_material(
        Decimal("1000.00"), Decimal("5.00"), DEFAULT_ABS, DEFAULT_PCT
    ) is True
    assert is_material(
        Decimal("500.00"), Decimal("10.00"), DEFAULT_ABS, DEFAULT_PCT
    ) is True
    assert is_material(
        Decimal("999.99"), Decimal("9.99"), DEFAULT_ABS, DEFAULT_PCT
    ) is False


def test_material_increase() -> None:
    current = [_line("revenue", "250000.00", name="Revenue")]
    prior = [_line("revenue", "210000.00", name="Revenue")]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    assert isinstance(result, VarianceAnalysisResult)
    item = _by_code(result, "revenue")
    assert item.line_item_name == "Revenue"
    assert item.current_amount == "250000.00"
    assert item.prior_amount == "210000.00"
    assert item.variance_amount == "40000.00"
    assert item.variance_pct == "19.05"
    assert item.direction == "increase"
    assert item.is_material is True

    payload = result.to_jsonb()
    assert payload["items"][0]["line_item_code"] == "revenue"
    assert "commentary" not in payload["items"][0]


def test_material_decrease() -> None:
    current = [_line("operating_expenses", "8000.00", name="Operating expenses")]
    prior = [_line("operating_expenses", "12000.00", name="Operating expenses")]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    item = _by_code(result, "operating_expenses")
    assert item.variance_amount == "-4000.00"
    assert item.variance_pct == "-33.33"
    assert item.direction == "decrease"
    assert item.is_material is True


def test_change_below_both_thresholds_not_material() -> None:
    """abs amount < 1000 and abs pct < 10 → not material."""
    current = [_line("cash", "10500.00", name="Cash")]
    prior = [_line("cash", "10000.00", name="Cash")]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    item = _by_code(result, "cash")
    assert item.variance_amount == "500.00"
    assert item.variance_pct == "5.00"
    assert item.direction == "increase"
    assert item.is_material is False


def test_zero_prior_balance_variance_pct_is_none() -> None:
    current = [_line("interest_income", "250.00", name="Interest income")]
    prior = [_line("interest_income", "0.00", name="Interest income")]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    item = _by_code(result, "interest_income")
    assert item.prior_amount == "0.00"
    assert item.variance_amount == "250.00"
    assert item.variance_pct is None
    assert item.direction == "increase"
    # Below absolute threshold and no pct → not material.
    assert item.is_material is False


def test_zero_prior_material_by_absolute_threshold_only() -> None:
    current = [_line("interest_income", "1500.00", name="Interest income")]
    prior = [_line("interest_income", "0.00", name="Interest income")]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    item = _by_code(result, "interest_income")
    assert item.variance_pct is None
    assert item.is_material is True


def test_new_line_item() -> None:
    current = [
        _line("revenue", "10000.00", name="Revenue"),
        _line("depreciation", "500.00", name="Depreciation"),
    ]
    prior = [_line("revenue", "10000.00", name="Revenue")]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    item = _by_code(result, "depreciation")
    assert item.direction == "new"
    assert item.current_amount == "500.00"
    assert item.prior_amount == "0.00"
    assert item.variance_amount == "500.00"
    assert item.variance_pct is None
    assert item.is_material is False


def test_removed_line_item() -> None:
    current = [_line("revenue", "10000.00", name="Revenue")]
    prior = [
        _line("revenue", "10000.00", name="Revenue"),
        _line("intangible_assets", "2000.00", name="Intangible assets"),
    ]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    item = _by_code(result, "intangible_assets")
    assert item.direction == "removed"
    assert item.current_amount == "0.00"
    assert item.prior_amount == "2000.00"
    assert item.variance_amount == "-2000.00"
    assert item.variance_pct == "-100.00"
    assert item.is_material is True


def test_subtotals_excluded_from_comparison() -> None:
    current = [
        _line("revenue", "12000.00", name="Revenue"),
        _line("cost_of_sales", "4000.00", name="Cost of sales"),
        _line("gross_profit", "8000.00", name="Gross profit", is_subtotal=True),
        _line("cash", "5000.00", name="Cash"),
        _line("total_assets", "5000.00", name="Total assets", is_subtotal=True),
    ]
    prior = [
        _line("revenue", "10000.00", name="Revenue"),
        _line("cost_of_sales", "4000.00", name="Cost of sales"),
        _line("gross_profit", "6000.00", name="Gross profit", is_subtotal=True),
        _line("cash", "5000.00", name="Cash"),
        _line("total_assets", "5000.00", name="Total assets", is_subtotal=True),
    ]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    codes = [item.line_item_code for item in result.items]
    assert "gross_profit" not in codes
    assert "total_assets" not in codes
    assert set(codes) == {"revenue", "cost_of_sales", "cash"}
    assert _by_code(result, "revenue").variance_amount == "2000.00"
    assert _by_code(result, "cost_of_sales").variance_amount == "0.00"


def test_per_client_thresholds_are_honoured() -> None:
    """Tight client thresholds can flag a change that defaults would ignore."""
    current = [_line("cash", "10500.00", name="Cash")]
    prior = [_line("cash", "10000.00", name="Cash")]

    default_result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )
    assert _by_code(default_result, "cash").is_material is False

    tight_result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=Decimal("5.00"),
        materiality_threshold_abs=Decimal("500.00"),
    )
    assert _by_code(tight_result, "cash").is_material is True


def test_matches_on_line_item_code_not_display_order() -> None:
    current = [
        _line("cash", "3000.00", name="Cash"),
        _line("revenue", "9000.00", name="Revenue"),
    ]
    prior = [
        _line("revenue", "8000.00", name="Revenue"),
        _line("cash", "2500.00", name="Cash"),
    ]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    assert _by_code(result, "revenue").variance_amount == "1000.00"
    assert _by_code(result, "cash").variance_amount == "500.00"


def test_both_nil_faces_omitted_from_variance() -> None:
    """Display parity with SOPL/SOFP nil-face filter: hide 0/0 leaf rows."""
    current = [
        _line("revenue", "10000.00", name="Revenue"),
        _line("dividends", "0.00", name="Dividends"),
        _line("social_security_payable", "0.00", name="Social security payable"),
    ]
    prior = [
        _line("revenue", "9000.00", name="Revenue"),
        _line("dividends", "0.00", name="Dividends"),
        _line("social_security_payable", "0.00", name="Social security payable"),
    ]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    codes = {item.line_item_code for item in result.items}
    assert codes == {"revenue"}
    assert _by_code(result, "revenue").variance_amount == "1000.00"


def test_one_sided_nil_still_shown() -> None:
    """Prior nil / current non-nil (and reverse) must remain visible."""
    current = [
        _line("interest_income", "250.00", name="Interest income"),
        _line("dividends", "0.00", name="Dividends"),
    ]
    prior = [
        _line("interest_income", "0.00", name="Interest income"),
        _line("dividends", "500.00", name="Dividends"),
    ]

    result = compute_variance(
        current,
        prior,
        materiality_threshold_pct=DEFAULT_PCT,
        materiality_threshold_abs=DEFAULT_ABS,
    )

    codes = {item.line_item_code for item in result.items}
    assert codes == {"interest_income", "dividends"}
    assert _by_code(result, "interest_income").direction == "increase"
    assert _by_code(result, "dividends").direction == "decrease"
