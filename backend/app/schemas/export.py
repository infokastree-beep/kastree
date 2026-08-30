"""Pydantic schemas for export API / exports table fields (§6.5 / §10.2 / §10.3)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

ExportFormat = Literal["xlsx", "csv", "pdf"]
ExportStatus = Literal["pending", "processing", "complete", "failed"]


class ExportOptions(BaseModel):
    """§6.5 option toggles. Tier/watermark are never part of options."""

    model_config = ConfigDict(extra="forbid")

    include_mapping_summary: bool = True
    include_risk_report: bool = True


class ExportCreateRequest(BaseModel):
    """POST /trial-balances/{id}/export body.

    subscription_tier / watermark may appear but are never applied — watermarking
    is driven solely by organisations.subscription_tier loaded from the DB via
    the TB's client.org_id (same class of protection as Organisations billing fields).
    """

    model_config = ConfigDict(extra="ignore")

    format: ExportFormat
    options: ExportOptions | None = None
    # Explicitly acknowledged + ignored by the router (not used for watermarking).
    subscription_tier: str | None = None
    watermark: bool | None = None


class ExportAcceptedResponse(BaseModel):
    """202 response mirroring §10.3 upload accepted shape."""

    model_config = ConfigDict(extra="forbid")

    export_id: uuid.UUID
    tb_id: uuid.UUID
    status: Literal["pending"]
    message: str


class ExportStatusResponse(BaseModel):
    """GET /exports/{id} status."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    tb_id: uuid.UUID
    format: ExportFormat
    status: ExportStatus
    file_url: str | None = None
    error_message: str | None = None
    options: dict | None = None


class ExportRecord(BaseModel):
    """exports row shape for API responses (Product Spec §9.1)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tb_id: str
    format: ExportFormat
    status: ExportStatus
    file_url: str | None = None
    error_message: str | None = None

    def to_jsonb(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude_none=True)


# Spoofable fields that must never influence watermarking / tier decisions.
TIER_FIELDS_NOT_FROM_REQUEST = frozenset(
    {
        "subscription_tier",
        "watermark",
        "subscription_status",
        "stripe_customer_id",
        "stripe_subscription_id",
    }
)
