"""Pydantic schemas for trial balance API and validation_results JSONB."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

CheckSeverity = Literal["error", "warning", "info"]


class ValidationCheck(BaseModel):
    """One validation check stored in trial_balances.validation_results.checks."""

    model_config = ConfigDict(extra="forbid")

    check_name: str
    passed: bool
    severity: CheckSeverity
    message: str


class ValidationResults(BaseModel):
    """Canonical shape for trial_balances.validation_results JSONB."""

    model_config = ConfigDict(extra="forbid")

    checks: list[ValidationCheck]

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB storage via SQLAlchemy."""
        return self.model_dump(mode="json")
