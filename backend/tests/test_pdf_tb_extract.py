"""Phase 1 PDF trial-balance extraction — native-text table + fail-closed paths."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
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
