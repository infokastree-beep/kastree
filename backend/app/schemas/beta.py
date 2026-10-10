"""First-practice beta responses. Sign-off and filing stay false."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class BetaPositionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: Literal["frs102-1a-ie"]
    wording_signed_off: Literal[False]
    self_review_required: Literal[True]
    filing_included: Literal[False]
    acknowledged: bool
    statement: str


class BetaAcknowledgementRequest(BaseModel):
    """The checkbox must be sent true on this request. It is not stored."""

    model_config = ConfigDict(extra="forbid")

    accepted: Literal[True]


class BetaAcknowledgementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recorded: bool
    acknowledged: Literal[True]
    wording_signed_off: Literal[False]
    filing_included: Literal[False]
    statement: str
