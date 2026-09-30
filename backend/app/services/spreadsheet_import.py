"""Spreadsheet and CSV text import for a worker, never for a request handler.

openpyxl is loaded with read_only=True. Row and column caps fail closed.
Formula-leading text is escaped before it can be written into an export.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal

import openpyxl  # type: ignore[import-untyped]

from app.services.upload_security import escape_formula_text

# The spec requires hard caps and does not set the numbers.
MAX_SHEET_ROWS = 50_000
MAX_SHEET_COLUMNS = 64


class SpreadsheetLimitError(Exception):
    """The sheet exceeds the row or column cap."""


def read_spreadsheet_text(content: bytes) -> list[list[str]]:
    """Read cell text from an xlsx. Does not evaluate formulas."""
    workbook = openpyxl.load_workbook(
        io.BytesIO(content),
        read_only=True,
        data_only=False,
    )
    try:
        rows: list[list[str]] = []
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                if len(rows) >= MAX_SHEET_ROWS:
                    raise SpreadsheetLimitError("Spreadsheet exceeds the row cap")
                values = tuple(row)
                if len(values) > MAX_SHEET_COLUMNS:
                    raise SpreadsheetLimitError("Spreadsheet exceeds the column cap")
                rows.append([_cell_text(value) for value in values])
        return rows
    finally:
        workbook.close()


def read_csv_text(content: bytes) -> list[list[str]]:
    """Read a CSV already accepted by the upload check."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SpreadsheetLimitError("CSV is not valid UTF-8") from exc
    rows: list[list[str]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(rows) >= MAX_SHEET_ROWS:
            raise SpreadsheetLimitError("Spreadsheet exceeds the row cap")
        if len(row) > MAX_SHEET_COLUMNS:
            raise SpreadsheetLimitError("Spreadsheet exceeds the column cap")
        rows.append([escape_formula_text(cell) for cell in row])
    return rows


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return escape_formula_text(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    return escape_formula_text(str(value))
