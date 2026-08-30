"""Pydantic schemas for export API / exports table fields."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

ExportFormat = Literal["xlsx", "csv", "pdf"]
ExportStatus = Literal["pending", "processing", "complete", "failed"]


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
