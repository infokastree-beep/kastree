"""Pydantic models for source-document upload."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SourceDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    detected_type: Literal["pdf", "xlsx", "csv"]
    byte_size: int
    sha256: str
    original_filename: str
    created_at: datetime
