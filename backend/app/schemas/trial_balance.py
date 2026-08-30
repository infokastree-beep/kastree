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
    details: dict[str, str] | None = None


_BLOCKING_CHECKS = frozenset(
    {"tb_integrity", "balance_sheet_balance", "net_assets"}
)


class ValidationResults(BaseModel):
    """Canonical shape for trial_balances.validation_results JSONB."""

    model_config = ConfigDict(extra="forbid")

    checks: list[ValidationCheck]

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB storage via SQLAlchemy."""
        return self.model_dump(mode="json", exclude_none=True)

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def can_generate_statements(self) -> bool:
        """True when every Error-severity blocking check passed (§4.2.1 / §10.3)."""
        by_name = {check.check_name: check for check in self.checks}
        return all(
            by_name[name].passed
            for name in _BLOCKING_CHECKS
            if name in by_name
        )
