"""Pydantic schemas for risk_flags rows (Product Spec §9.1, Appendix D)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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


class RiskFlagResponse(BaseModel):
    """One flag in GET/POST /trial-balances/{id}/risk (§10.2 heatmap)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    rule_name: str
    severity: RiskSeverity
    description: str
    affected_accounts: list[AffectedAccount] | None = None
    recommended_action: str | None = None


class RiskFlagsResponse(BaseModel):
    """GET/POST /trial-balances/{id}/risk response."""

    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    flags: list[RiskFlagResponse] = Field(default_factory=list)
    # MVP: no monthly-history table — Rule 2 always receives empty history (§4.3).
    unusual_variance_history_months: int = 0
