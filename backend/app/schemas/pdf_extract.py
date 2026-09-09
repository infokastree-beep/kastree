"""Schemas for Phase 1 PDF trial-balance extraction (review-before-pipeline)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, PlainSerializer

# Serialize money as strings so JSON never float-contaminates review amounts.
MoneyStr = Annotated[
    Decimal,
    PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json"),
]


class ExtractedTbRowOut(BaseModel):
    account_code: str
    account_name: str
    debit: MoneyStr
    credit: MoneyStr
    row_index: int


class PdfTbExtractResponse(BaseModel):
    """Candidate rows for the upload review UI — not yet a TrialBalance."""

    rows: list[ExtractedTbRowOut]
    method: Literal["pdfplumber_table", "pdfplumber_words", "ocr_tesseract"]
    page_count: int
    warnings: list[str] = Field(default_factory=list)
    message: str = (
        "Review and correct the extracted rows, then confirm to continue "
        "with the normal upload pipeline."
    )
