"""Pydantic schemas for AI commentary JSONB (Product Spec §4.3, §10.3)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ConfidenceLevel = Literal["high", "medium", "low"]


class CommentaryRecord(BaseModel):
    """Per-line commentary shape from GET /trial-balances/{id}/variance (§10.3)."""

    model_config = ConfigDict(extra="forbid")

    text: str
    is_ai_generated: bool = True
    is_edited: bool = False
    reasoning: str
    confidence: ConfidenceLevel


class VarianceCommentaryResult(BaseModel):
    """Canonical shape for variance_analyses.commentary (material variance texts).

    Keys are line_item_code; values match the nested ``commentary`` object in §10.3.
    """

    model_config = ConfigDict(extra="forbid")

    commentaries: dict[str, CommentaryRecord]

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB storage via SQLAlchemy."""
        return self.model_dump(mode="json", exclude_none=True)


class BusinessHealthResult(BaseModel):
    """AI Business Health summary (Product Spec §4.3)."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    key_points: list[str]
    confidence: ConfidenceLevel
    is_ai_generated: bool = True
    is_edited: bool = False
    # BUSINESS_HEALTH_SYSTEM does not request reasoning; kept optional for display parity.
    reasoning: str | None = None

    def to_jsonb(self) -> dict[str, object]:
        """Serialize for PostgreSQL JSONB / API payloads."""
        return self.model_dump(mode="json", exclude_none=True)
