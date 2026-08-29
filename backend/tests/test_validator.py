"""Tests for trial balance validation_results Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.trial_balance import ValidationCheck, ValidationResults


def test_validation_results_serializes_check_name_key() -> None:
    results = ValidationResults(
        checks=[
            ValidationCheck(
                check_name="tb_integrity",
                passed=True,
                severity="error",
                message="Trial balance debits equal credits.",
            ),
            ValidationCheck(
                check_name="net_assets",
                passed=False,
                severity="error",
                message="Net assets mismatch.",
            ),
        ]
    )

    payload = results.to_jsonb()

    assert payload == {
        "checks": [
            {
                "check_name": "tb_integrity",
                "passed": True,
                "severity": "error",
                "message": "Trial balance debits equal credits.",
            },
            {
                "check_name": "net_assets",
                "passed": False,
                "severity": "error",
                "message": "Net assets mismatch.",
            },
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
