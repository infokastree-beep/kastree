"""Tests for trial balance validation_results Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.trial_balance import ValidationCheck, ValidationResults


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
