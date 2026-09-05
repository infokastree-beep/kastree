"""Pydantic schemas for AI commentary JSONB and feedback API (§4.3 / §10.2 / §10.3)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConfidenceLevel = Literal["high", "medium", "low"]


class CommentaryRecord(BaseModel):
    """Per-line commentary shape from GET /trial-balances/{id}/variance (§10.3).

    When a user corrects text, ``original_text`` holds the prior AI wording
    (§7 — original AI text preserved); ``text`` becomes the corrected version.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    is_ai_generated: bool = True
    is_edited: bool = False
    reasoning: str
    confidence: ConfidenceLevel
    edited_by_user_id: uuid.UUID | None = None
    original_text: str | None = None


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


class BusinessHealthGenerateRequest(BaseModel):
    """Optional explicit prior TB; omit to auto-detect (§6.2)."""

    model_config = ConfigDict(extra="forbid")

    prior_tb_id: uuid.UUID | None = None


class BusinessHealthResponse(BaseModel):
    """POST /trial-balances/{id}/business-health response.

    On success ``available`` is True and the nested ``health`` payload matches
    ``BusinessHealthResult`` (summary + 3 key_points + confidence). When prior
    period or prior statements are missing, ``available`` is False and
    ``health`` is None — same fail-soft pattern as variance.
    """

    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    prior_tb_id: uuid.UUID | None = None
    available: bool
    message: str | None = None
    health: BusinessHealthResult | None = None


MISSING_PRIOR_FOR_HEALTH_MESSAGE = (
    "Not enough history yet — upload a prior period TB to enable the "
    "business health summary."
)

PRIOR_STATEMENTS_MISSING_FOR_HEALTH_MESSAGE = (
    "Prior period statements have not been generated yet. "
    "Generate statements for the prior trial balance to enable the "
    "business health summary."
)


class CommentaryFeedbackRequest(BaseModel):
    """POST /commentary/feedback body."""

    model_config = ConfigDict(extra="forbid")

    variance_id: uuid.UUID
    line_item_code: str = Field(min_length=1, max_length=200)
    thumbs_up: bool | None = None
    corrected_text: str | None = Field(default=None, max_length=10000)


class CommentaryFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    variance_id: uuid.UUID
    user_id: uuid.UUID
    line_item_code: str
    thumbs_up: bool | None
    corrected_text: str | None
    created_at: datetime
    commentary_updated: bool = False
