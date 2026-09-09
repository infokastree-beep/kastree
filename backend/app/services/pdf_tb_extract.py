"""Phase 1: extract trial-balance rows from a PDF for human review.

Library choice (environment-constrained):
- Primary: ``pdfplumber`` — layout-aware table extraction from native-text PDFs
  (character positions + ruling lines). Pure Python stack (pdfminer); no Java /
  Ghostscript. Fits Railway slim images and this repo's WeasyPrint-based PDF
  tooling already present.
- OCR fallback: ``PyMuPDF`` renders pages to images + ``Tesseract``
  (``pytesseract``) when the PDF has little extractable text or no usable
  table. System packages: ``tesseract-ocr``, ``tesseract-ocr-eng``.

Golden Rule: extraction yields candidate rows only. Amounts are parsed with
Decimal via :func:`parse_monetary`. The user must confirm the review table
before anything enters the existing parse → map pipeline (typically as CSV).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
from typing import Literal

import pdfplumber
from pdfplumber.page import Page

from app.services.parser import ParseError, parse_monetary

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF"
MIN_EXTRACTED_ROWS = 3
# Below this many alphabetic/printable chars across the doc → likely scanned.
MIN_NATIVE_TEXT_CHARS = 20
OCR_RENDER_DPI = 200
# Tesseract degrades on extremely large bitmaps (blank / garbage). Cap the
# longest side before OCR; scanned A4 at 200dpi is ~1700px wide.
OCR_MAX_IMAGE_SIDE = 2000

ExtractMethod = Literal["pdfplumber_table", "pdfplumber_words", "ocr_tesseract"]


@dataclass(frozen=True)
class ExtractedTBRow:
    """One candidate TB line for the review UI (pre-pipeline)."""

    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    row_index: int


@dataclass(frozen=True)
class PdfTbExtractResult:
    rows: list[ExtractedTBRow]
    method: ExtractMethod
    page_count: int
    warnings: list[str]


class PdfTbExtractError(Exception):
    """Fail-closed extraction — caller maps to HTTP 422."""


def extract_trial_balance_from_pdf(content: bytes) -> PdfTbExtractResult:
    """Extract TB-like rows from a PDF. Raises :class:`PdfTbExtractError` on failure."""
    if not content.startswith(PDF_MAGIC):
        raise PdfTbExtractError(
            "This file is not a valid PDF (missing %PDF header). "
            "Export a PDF trial balance, or upload .xlsx / .csv instead."
        )

    warnings: list[str] = []
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise PdfTbExtractError("PDF has no pages.")

            native_chars = sum(len(page.extract_text() or "") for page in pdf.pages)
            table_rows = _extract_via_tables(pdf.pages)
            if len(table_rows) >= MIN_EXTRACTED_ROWS:
                return PdfTbExtractResult(
                    rows=table_rows,
                    method="pdfplumber_table",
                    page_count=page_count,
                    warnings=warnings,
                )

            word_rows = _extract_via_words(pdf.pages)
            if len(word_rows) >= MIN_EXTRACTED_ROWS:
                warnings.append(
                    "No clear table grid detected; rows inferred from text positions."
                )
                return PdfTbExtractResult(
                    rows=word_rows,
                    method="pdfplumber_words",
                    page_count=page_count,
                    warnings=warnings,
                )

            if native_chars >= MIN_NATIVE_TEXT_CHARS:
                raise PdfTbExtractError(
                    "Could not detect a trial-balance table in this PDF. "
                    "Check that the file shows account code, name, debit, and "
                    "credit columns, or upload .xlsx / .csv instead."
                )
    except PdfTbExtractError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface as extraction failure
        logger.exception("pdfplumber extraction failed")
        raise PdfTbExtractError(
            f"Could not read this PDF ({type(exc).__name__}). "
            "Try a different export or upload .xlsx / .csv."
        ) from exc

    warnings.append("Little native text detected — used OCR (scanned PDF fallback).")
    ocr_rows, ocr_pages = _extract_via_ocr(content)
    if len(ocr_rows) < MIN_EXTRACTED_ROWS:
        raise PdfTbExtractError(
            "OCR could not find enough trial-balance rows. "
            "Upload a clearer scan, or use .xlsx / .csv."
        )
    return PdfTbExtractResult(
        rows=ocr_rows,
        method="ocr_tesseract",
        page_count=ocr_pages,
        warnings=warnings,
    )


def _extract_via_tables(pages: list[Page]) -> list[ExtractedTBRow]:
    best: list[list[str | None]] = []
    best_score = -1
    for page in pages:
        for table in page.extract_tables() or []:
            if not table or len(table) < MIN_EXTRACTED_ROWS + 1:
                continue
            score = _score_table(table)
            if score > best_score:
                best_score = score
                best = table
    if best_score < 1 or not best:
        return []
    return _rows_from_table_matrix(best)


def _score_table(table: list[list[str | None]]) -> int:
    """Higher = more likely a TB (headers + numeric columns)."""
    if not table:
        return 0
    header = " ".join(str(c or "").lower() for c in table[0])
    score = 0
    for token in (
        "account",
        "code",
        "name",
        "description",
        "debit",
        "credit",
        "balance",
    ):
        if token in header:
            score += 2
    # Prefer tables with 3–5 columns (code/name/debit/credit or +balance).
    width = max(len(r) for r in table)
    if 3 <= width <= 6:
        score += 1
    numericish = 0
    for row in table[1:6]:
        for cell in row:
            text = str(cell or "").strip()
            if re.search(r"\d", text) and re.search(r"[£€$,.\d]", text):
                numericish += 1
    score += min(numericish, 6)
    return score


def _rows_from_table_matrix(table: list[list[str | None]]) -> list[ExtractedTBRow]:
    header_idx, column_map = _detect_header_and_columns(table)
    if column_map is None:
        return []
    out: list[ExtractedTBRow] = []
    for offset, raw in enumerate(table[header_idx + 1 :], start=1):
        cells = [str(c or "").strip() for c in raw]
        if not any(cells):
            continue
        if _looks_like_totals_row(cells):
            continue
        try:
            row = _build_row(cells, column_map, row_index=offset)
        except (ParseError, PdfTbExtractError):
            continue
        if not row.account_code and not row.account_name:
            continue
        if row.debit == Decimal("0") and row.credit == Decimal("0"):
            # Keep zero rows only when they have an account identity (opening
            # nils are rare; skip blank noise).
            if not row.account_name:
                continue
        out.append(row)
    return out


def _detect_header_and_columns(
    table: list[list[str | None]],
) -> tuple[int, dict[str, int] | None]:
    for idx, raw in enumerate(table[:5]):
        cells = [str(c or "").strip().lower() for c in raw]
        joined = " ".join(cells)
        if not any(
            token in joined
            for token in ("account", "debit", "credit", "code", "description")
        ):
            continue
        mapping: dict[str, int] = {}
        for col_i, cell in enumerate(cells):
            if "code" in cell and "account" in cell:
                mapping.setdefault("account_code", col_i)
            elif cell in {"code", "a/c", "ac", "no", "number"} or (
                "code" in cell and "name" not in cell
            ):
                mapping.setdefault("account_code", col_i)
            elif any(
                t in cell for t in ("name", "description", "particular", "account")
            ):
                # Prefer explicit name/description over bare "account".
                if "name" in cell or "description" in cell or "particular" in cell:
                    mapping["account_name"] = col_i
                else:
                    mapping.setdefault("account_name", col_i)
            elif "debit" in cell or cell in {"dr", "dr."}:
                mapping.setdefault("debit", col_i)
            elif "credit" in cell or cell in {"cr", "cr."}:
                mapping.setdefault("credit", col_i)
            elif "balance" in cell and "debit" not in cell and "credit" not in cell:
                mapping.setdefault("balance", col_i)
        if "debit" in mapping and "credit" in mapping:
            mapping.setdefault("account_code", 0)
            mapping.setdefault("account_name", 1 if mapping.get("account_code") == 0 else 0)
            return idx, mapping
        if "balance" in mapping:
            mapping.setdefault("account_code", 0)
            mapping.setdefault("account_name", 1)
            return idx, mapping
    # No header — assume four-column layout on first data-looking row.
    if table and len(table[0]) >= 4:
        return -1, {
            "account_code": 0,
            "account_name": 1,
            "debit": 2,
            "credit": 3,
        }
    if table and len(table[0]) == 3:
        return -1, {"account_code": 0, "account_name": 1, "balance": 2}
    return 0, None


def _build_row(
    cells: list[str],
    column_map: dict[str, int],
    *,
    row_index: int,
) -> ExtractedTBRow:
    def cell(key: str) -> str:
        i = column_map.get(key)
        if i is None or i >= len(cells):
            return ""
        return cells[i]

    code = cell("account_code")
    name = cell("account_name")
    if "debit" in column_map and "credit" in column_map:
        debit = parse_monetary(cell("debit"), row_index=row_index, column_name="debit")
        credit = parse_monetary(
            cell("credit"), row_index=row_index, column_name="credit"
        )
    else:
        balance = parse_monetary(
            cell("balance"), row_index=row_index, column_name="balance"
        )
        if balance >= Decimal("0"):
            debit, credit = balance, Decimal("0")
        else:
            debit, credit = Decimal("0"), abs(balance)
    return ExtractedTBRow(
        account_code=code,
        account_name=name or code,
        debit=debit,
        credit=credit,
        row_index=row_index,
    )


def _looks_like_totals_row(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    return any(token in joined for token in ("total", "totals", "grand total", "sum"))


def _extract_via_words(pages: list[Page]) -> list[ExtractedTBRow]:
    """Fallback: cluster words into lines, then split code / name / amounts."""
    lines: list[str] = []
    for page in pages:
        words = page.extract_words(use_text_flow=True) or []
        if not words:
            text = page.extract_text() or ""
            lines.extend(text.splitlines())
            continue
        # Group by rounded top coordinate.
        buckets: dict[int, list[dict[str, object]]] = {}
        for word in words:
            top = int(round(float(word["top"]) / 3.0) * 3)
            buckets.setdefault(top, []).append(word)
        for top in sorted(buckets):
            ordered = sorted(buckets[top], key=lambda w: float(w["x0"]))
            lines.append(" ".join(str(w["text"]) for w in ordered))
    return _rows_from_text_lines(lines)


def _extract_via_ocr(content: bytes) -> tuple[list[ExtractedTBRow], int]:
    """Render pages and OCR. Returns (rows, page_count).

    Uses Tesseract ``--psm 4`` (single column of variable-size text) first —
    default OSD often splits Debit/Credit into vertical columns and shreds
    amounts. Falls back to ``--psm 6`` then word-box line reconstruction.
    """
    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
    except ImportError as exc:  # pragma: no cover — deps declared in requirements
        raise PdfTbExtractError(
            "OCR dependencies are not installed on this server."
        ) from exc

    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise PdfTbExtractError("Could not open PDF for OCR.") from exc

    page_count = len(doc)
    best_rows: list[ExtractedTBRow] = []
    best_score = (-1, -1)

    def _consider(rows: list[ExtractedTBRow]) -> None:
        nonlocal best_rows, best_score
        coded = sum(1 for row in rows if row.account_code)
        score = (len(rows), coded)
        if score > best_score:
            best_score = score
            best_rows = rows

    try:
        for page in doc:
            pix = page.get_pixmap(dpi=OCR_RENDER_DPI)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            longest = max(image.size)
            if longest > OCR_MAX_IMAGE_SIDE:
                scale = OCR_MAX_IMAGE_SIDE / float(longest)
                image = image.resize(
                    (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            for config in ("--psm 4", "--psm 6"):
                text = pytesseract.image_to_string(image, config=config)
                _consider(_rows_from_text_lines(text.splitlines()))
            # Reconstruct lines from word boxes (handles column-wise OCR).
            data = pytesseract.image_to_data(
                image, config="--psm 4", output_type=pytesseract.Output.DICT
            )
            buckets: dict[int, list[tuple[int, str]]] = {}
            n = len(data["text"])
            for i in range(n):
                word = str(data["text"][i] or "").strip()
                if not word:
                    continue
                top = int(round(int(data["top"][i]) / 10.0) * 10)
                left = int(data["left"][i])
                buckets.setdefault(top, []).append((left, word))
            reconstructed = [
                " ".join(w for _, w in sorted(items))
                for _, items in sorted(buckets.items())
            ]
            _consider(_rows_from_text_lines(reconstructed))
    finally:
        doc.close()
    return best_rows, page_count


def _rows_from_text_lines(lines: list[str]) -> list[ExtractedTBRow]:
    out: list[ExtractedTBRow] = []
    row_index = 0
    for line in lines:
        cleaned = " ".join(line.split())
        # OCR often inserts a space in decimals: "25000. 00" → "25000.00"
        cleaned = re.sub(r"(\d)\.\s+(\d{1,2})\b", r"\1.\2", cleaned)
        if not cleaned or _looks_like_totals_row([cleaned]):
            continue
        lower = cleaned.lower()
        if any(
            h in lower
            for h in ("account code", "account name", "debit", "credit", "trial balance")
        ) and not re.search(r"\d{3,}", cleaned):
            continue
        parsed = _parse_text_line(cleaned)
        if parsed is None:
            continue
        row_index += 1
        out.append(
            ExtractedTBRow(
                account_code=parsed[0],
                account_name=parsed[1],
                debit=parsed[2],
                credit=parsed[3],
                row_index=row_index,
            )
        )
    return out


_AMOUNT_TOKEN = re.compile(
    r"^\(?-?[£€$]?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\)?$|"
    r"^\(?-?[£€$]?\d+(?:\.\d{1,2})?\)?$"
)
# Strong money: currency, thousands separator, decimal, or parentheses —
# excludes bare account codes like "1000".
_STRONG_MONEY = re.compile(
    r"[£€$,]|^\(?-?\d+\.\d{1,2}\)?$|^\(.*\)$"
)
_LEADING_ACCOUNT_CODE = re.compile(r"^[A-Za-z0-9./-]{2,20}$")


def rows_to_csv_bytes(rows: list[ExtractedTBRow]) -> bytes:
    """Serialize extracted rows to a four-column CSV for the existing parser."""
    lines = ["Account Code,Account Name,Debit,Credit"]
    for row in rows:
        code = _csv_escape(row.account_code)
        name = _csv_escape(row.account_name)
        lines.append(f"{code},{name},{row.debit},{row.credit}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _csv_escape(value: str) -> str:
    if any(ch in value for ch in '",\n'):
        return '"' + value.replace('"', '""') + '"'
    return value


def _is_strong_money_token(token: str) -> bool:
    cleaned = token.replace(" ", "")
    if not _AMOUNT_TOKEN.match(cleaned):
        return False
    return bool(_STRONG_MONEY.search(cleaned))


def _parse_text_line(
    line: str,
) -> tuple[str, str, Decimal, Decimal] | None:
    """Best-effort: leading code, trailing one or two amounts, name in middle."""
    tokens = line.split()
    if len(tokens) < 2:
        return None

    # Peel a leading account code before amount detection so "1000" is not
    # mistaken for a monetary amount.
    code = ""
    body = tokens
    if _LEADING_ACCOUNT_CODE.match(tokens[0]) and re.search(r"\d", tokens[0]):
        if not _is_strong_money_token(tokens[0]):
            code = tokens[0]
            body = tokens[1:]
    if not body:
        return None

    strong: list[tuple[int, Decimal]] = []
    weak: list[tuple[int, Decimal]] = []
    for i, token in enumerate(body):
        cleaned = token.replace(" ", "")
        if not _AMOUNT_TOKEN.match(cleaned):
            continue
        try:
            value = parse_monetary(token)
        except ParseError:
            continue
        if _is_strong_money_token(token):
            strong.append((i, value))
        else:
            weak.append((i, value))

    # After peeling the account code, bare integers in the body are amounts
    # (e.g. OCR reading "0.00" as "0000"). Prefer strong money, but fill from
    # weak so debit/credit pairs still form when OCR is imperfect.
    if len(strong) >= 2:
        amounts = strong
    elif len(strong) == 1:
        before = [item for item in weak if item[0] < strong[0][0]]
        after = [item for item in weak if item[0] > strong[0][0]]
        amounts = before + strong + after
    else:
        amounts = weak
    if not amounts:
        return None
    # Use last one or two amount tokens.
    if len(amounts) >= 2:
        (_, debit), (_, credit) = amounts[-2], amounts[-1]
        cut = amounts[-2][0]
    else:
        balance = amounts[-1][1]
        cut = amounts[-1][0]
        if balance >= Decimal("0"):
            debit, credit = balance, Decimal("0")
        else:
            debit, credit = Decimal("0"), abs(balance)
    name_tokens = body[:cut]
    if not code and name_tokens:
        if _LEADING_ACCOUNT_CODE.match(name_tokens[0]) and re.search(
            r"\d", name_tokens[0]
        ):
            if not _is_strong_money_token(name_tokens[0]):
                code = name_tokens[0]
                name_tokens = name_tokens[1:]
    name = " ".join(name_tokens).strip() or code
    if not name:
        return None
    return code, name, debit, credit
