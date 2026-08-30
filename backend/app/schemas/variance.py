"""Pydantic schemas for variance_analyses.items JSONB (Product Spec §10.3)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

VarianceDirection = Literal["increase", "decrease", "new", "removed"]


class VarianceItemRecord(BaseModel):
    """One variance row stored in variance_analyses.items (minus commentary)."""

    model_config = ConfigDict(extra="forbid")

    line_item_code: str
    line_item_name: str
    current_amount: str
    prior_amount: str
    variance_amount: str
    variance_pct: str | None = None
    direction: VarianceDirection
    is_material: bool


class VarianceAnalysisResult(BaseModel):
    """Canonical shape for variance_analyses.items JSONB payload."""

    model_config = ConfigDict(extra="forbid")

    items: list[VarianceItemRecord]

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB storage via SQLAlchemy."""
        return self.model_dump(mode="json", exclude_none=True)
