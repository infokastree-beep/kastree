"""Pydantic schemas for risk_flags rows (Product Spec §9.1, Appendix D)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

RiskSeverity = Literal["warning", "critical"]


class AffectedAccount(BaseModel):
    """One TB account listed on a risk flag's affected_accounts JSONB."""

    model_config = ConfigDict(extra="forbid")

    account_code: str
    account_name: str
    net_balance: str


class RiskFlagRecord(BaseModel):
    """One risk_flags row ready for persistence (minus tb_id / timestamps)."""

    model_config = ConfigDict(extra="forbid")

    rule_name: str
    severity: RiskSeverity
    description: str
    affected_accounts: list[AffectedAccount] | None = None
    recommended_action: str | None = None

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB / API payloads via SQLAlchemy."""
        return self.model_dump(mode="json", exclude_none=True)
