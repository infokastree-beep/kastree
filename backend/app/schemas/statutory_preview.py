"""Section preview. The HTML is escaped composer output, not a second renderer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PreviewChildOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    number: int | None = None
    label: str
    anchor: str


class StatutoryPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    anchor: str
    row_version: int = Field(ge=0)
    preview_revision: str
    watermark: str
    html: str
    section_html_sha256: str
    children: list[PreviewChildOut]
