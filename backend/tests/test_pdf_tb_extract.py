"""Phase 1 PDF trial-balance extraction — native, messy, OCR, and fail-closed."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import fitz
import pdfplumber
import pytest
from PIL import Image, ImageDraw, ImageFont
from weasyprint import HTML

from app.services.parser import parse_tb_file
from app.services.pdf_tb_extract import (
    PdfTbExtractError,
    extract_trial_balance_from_pdf,
    rows_to_csv_bytes,
)


def _realistic_tb_pdf_bytes() -> bytes:
    """Native-text PDF with a real HTML table (account / debit / credit)."""
    html = """
    <html><head><style>
      body { font-family: sans-serif; font-size: 11pt; }
      h1 { font-size: 14pt; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #333; padding: 4px 8px; }
      td.num { text-align: right; }
    </style></head><body>
      <h1>Demo Trading Ltd — Trial Balance as at 31 December 2025</h1>
      <table>
        <thead>
          <tr>
            <th>Account Code</th>
            <th>Account Name</th>
            <th>Debit</th>
            <th>Credit</th>
          </tr>
        </thead>
        <tbody>
          <tr><td>1000</td><td>Bank Current Account</td><td class="num">12,500.00</td><td class="num">0.00</td></tr>
          <tr><td>1100</td><td>Trade Receivables</td><td class="num">8,250.50</td><td class="num">0.00</td></tr>
          <tr><td>2000</td><td>Trade Payables</td><td class="num">0.00</td><td class="num">4,100.00</td></tr>
          <tr><td>3000</td><td>Share Capital</td><td class="num">0.00</td><td class="num">10,000.00</td></tr>
          <tr><td>3100</td><td>Retained Earnings</td><td class="num">0.00</td><td class="num">3,150.50</td></tr>
          <tr><td>4000</td><td>Sales Revenue</td><td class="num">0.00</td><td class="num">25,000.00</td></tr>
          <tr><td>5000</td><td>Cost of Sales</td><td class="num">9,500.00</td><td class="num">0.00</td></tr>
          <tr><td>6000</td><td>Operating Expenses</td><td class="num">12,000.00</td><td class="num">0.00</td></tr>
          <tr><td colspan="2"><strong>Total</strong></td><td class="num">42,250.50</td><td class="num">42,250.50</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    return HTML(string=html).write_pdf()


def _messy_native_text_pdf_bytes() -> bytes:
    """Imperfect formatting: no table grid, uneven spacing, currency symbols.

    Exercises the words / text-line path rather than clean table detection.
    """
    html = """
    <html><head><style>
      body { font-family: monospace; font-size: 10pt; line-height: 1.6; }
      pre { white-space: pre-wrap; }
    </style></head><body>
      <p>Messy Co Ltd - Trial Balance 31/12/2025 (exported print layout)</p>
      <pre>
Account Code   Account Name                 Debit          Credit
1000   Bank Current Account              £12,500.00            £0.00
1100   Trade Receivables                  8,250.50             0.00
2000   Trade Payables                         0.00         4,100.00
3000   Share Capital                          0.00        10,000.00
3100   Retained Earnings                      0.00         3,150.50
4000   Sales Revenue                          0.00        25,000.00
5000   Cost of Sales                      9,500.00             0.00
6000   Operating Expenses                12,000.00             0.00
      </pre>
    </body></html>
    """
    return HTML(string=html).write_pdf()


def _scanned_image_only_tb_pdf_bytes() -> bytes:
    """Image-only PDF (no text layer) — forces the OCR fallback path.

    Larger monospace layout with grid lines so Tesseract can recover rows;
    still zero native text (verified by callers).
    """
    img = Image.new("RGB", (1400, 700), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 24
        )
    except OSError:  # pragma: no cover
        font = ImageFont.load_default()

    rows = [
        ["Account Code", "Account Name", "Debit", "Credit"],
        ["1000", "Bank Current Account", "12500.00", "0.00"],
        ["1100", "Trade Receivables", "8250.50", "0.00"],
        ["2000", "Trade Payables", "0.00", "4100.00"],
        ["3000", "Share Capital", "0.00", "10000.00"],
        ["3100", "Retained Earnings", "0.00", "3150.50"],
        ["4000", "Sales Revenue", "0.00", "25000.00"],
        ["5000", "Cost of Sales", "9500.00", "0.00"],
        ["6000", "Operating Expenses", "12000.00", "0.00"],
    ]
    cols = [40, 230, 880, 1120]
    row_h = 60
    top = 40
    for i in range(len(rows) + 1):
        y = top + i * row_h
        draw.line([(30, y), (1340, y)], fill="#333", width=2)
    for x in (30, 220, 870, 1110, 1340):
        draw.line([(x, top), (x, top + len(rows) * row_h)], fill="#333", width=2)
    for ri, row in enumerate(rows):
        y = top + ri * row_h + 18
        for ci, cell in enumerate(row):
            draw.text((cols[ci], y), cell, fill="black", font=font)

    doc = fitz.open()
    # Letter-size page with the scan image fitted (realistic scanned PDF).
    page = doc.new_page(width=612, height=792)
    buf = BytesIO()
    img.save(buf, format="PNG")
    page.insert_image(page.rect, stream=buf.getvalue())
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_extract_realistic_native_text_tb_pdf() -> None:
    content = _realistic_tb_pdf_bytes()
    assert content.startswith(b"%PDF")
    result = extract_trial_balance_from_pdf(content)
    assert result.method == "pdfplumber_table"
    assert result.page_count >= 1
    assert len(result.rows) >= 8

    by_code = {row.account_code: row for row in result.rows}
    assert "1000" in by_code
    assert "Bank Current" in by_code["1000"].account_name or "Bank" in by_code["1000"].account_name
    assert by_code["1000"].debit == Decimal("12500.00")
    assert by_code["1000"].credit == Decimal("0.00")
    assert by_code["4000"].credit == Decimal("25000.00")
    assert by_code["5000"].debit == Decimal("9500.00")
    # Totals row must not appear as an account.
    assert not any("total" in r.account_name.lower() for r in result.rows)

    total_debits = sum((r.debit for r in result.rows), Decimal("0"))
    total_credits = sum((r.credit for r in result.rows), Decimal("0"))
    assert total_debits == total_credits == Decimal("42250.50")


def test_extract_messy_native_text_without_table_grid() -> None:
    content = _messy_native_text_pdf_bytes()
    result = extract_trial_balance_from_pdf(content)
    assert result.method in {"pdfplumber_table", "pdfplumber_words"}
    assert len(result.rows) >= 8
    by_code = {row.account_code: row for row in result.rows}
    assert by_code["1000"].debit == Decimal("12500.00")
    assert by_code["2000"].credit == Decimal("4100.00")
    assert by_code["6000"].debit == Decimal("12000.00")
    total_debits = sum((r.debit for r in result.rows), Decimal("0"))
    total_credits = sum((r.credit for r in result.rows), Decimal("0"))
    assert total_debits == total_credits == Decimal("42250.50")


def test_extract_scanned_image_only_pdf_uses_ocr_fallback() -> None:
    content = _scanned_image_only_tb_pdf_bytes()
    with pdfplumber.open(BytesIO(content)) as pdf:
        native = "".join((page.extract_text() or "") for page in pdf.pages)
    assert len(native.strip()) < 20  # no usable text layer

    result = extract_trial_balance_from_pdf(content)
    assert result.method == "ocr_tesseract"
    assert any("OCR" in w or "scanned" in w.lower() for w in result.warnings)
    assert len(result.rows) >= 8

    by_code = {row.account_code: row for row in result.rows}
    assert "1000" in by_code
    assert by_code["1000"].debit == Decimal("12500.00")
    assert by_code["4000"].credit == Decimal("25000.00")
    total_debits = sum((r.debit for r in result.rows), Decimal("0"))
    total_credits = sum((r.credit for r in result.rows), Decimal("0"))
    assert total_debits == total_credits == Decimal("42250.50")


def test_extract_rejects_non_pdf_magic() -> None:
    with pytest.raises(PdfTbExtractError, match="not a valid PDF"):
        extract_trial_balance_from_pdf(b"PK\x03\x04not-a-pdf")


def test_extract_rejects_emptyish_pdf() -> None:
    html = "<html><body><p>Hello — no trial balance here.</p></body></html>"
    content = HTML(string=html).write_pdf()
    with pytest.raises(PdfTbExtractError, match="Could not detect"):
        extract_trial_balance_from_pdf(content)


def test_extracted_csv_handoff_parses_via_existing_parser() -> None:
    """Confirm path: PDF extract → CSV bytes → unchanged parse_tb_file."""
    content = _realistic_tb_pdf_bytes()
    result = extract_trial_balance_from_pdf(content)
    csv_bytes = rows_to_csv_bytes(result.rows)
    parsed = parse_tb_file(csv_bytes, filename="extracted-trial-balance.csv")
    assert len(parsed) == len(result.rows)
    by_code = {row.account_code: row for row in parsed}
    assert by_code["1000"].debit == Decimal("12500.00")
    assert by_code["4000"].credit == Decimal("25000.00")
    total_debits = sum((r.debit for r in parsed), Decimal("0"))
    total_credits = sum((r.credit for r in parsed), Decimal("0"))
    assert total_debits == total_credits == Decimal("42250.50")
