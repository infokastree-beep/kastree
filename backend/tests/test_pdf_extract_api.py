"""API guarantees: extract-pdf never creates a TB; /upload rejects PDFs."""

from __future__ import annotations

from io import BytesIO

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from weasyprint import HTML

from app.db import SyncSessionLocal, set_rls_org_id
from tests.conftest import auth_headers


def _clean_tb_pdf() -> bytes:
    html = """
    <html><body>
      <h1>Gate Test Ltd — Trial Balance</h1>
      <table border="1">
        <tr><th>Account Code</th><th>Account Name</th><th>Debit</th><th>Credit</th></tr>
        <tr><td>1000</td><td>Bank</td><td>1000.00</td><td>0.00</td></tr>
        <tr><td>1100</td><td>Receivables</td><td>500.00</td><td>0.00</td></tr>
        <tr><td>2000</td><td>Payables</td><td>0.00</td><td>300.00</td></tr>
        <tr><td>3000</td><td>Capital</td><td>0.00</td><td>1200.00</td></tr>
        <tr><td>4000</td><td>Sales</td><td>0.00</td><td>2000.00</td></tr>
        <tr><td>5000</td><td>COS</td><td>800.00</td><td>0.00</td></tr>
        <tr><td>6000</td><td>Opex</td><td>1200.00</td><td>0.00</td></tr>
      </table>
    </body></html>
    """
    return HTML(string=html).write_pdf()


@pytest.mark.asyncio
async def test_extract_pdf_does_not_create_trial_balance(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Even a perfectly clean PDF extract must not touch trial_balances."""
    headers = auth_headers(provisioned_org["token"])
    org_id = provisioned_org["org_id"]

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        before = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()

    pdf = _clean_tb_pdf()
    resp = await api_client.post(
        "/trial-balances/extract-pdf",
        files={"file": ("clean-tb.pdf", BytesIO(pdf), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["rows"]) >= 7
    assert body["method"] in {
        "pdfplumber_table",
        "pdfplumber_words",
        "ocr_tesseract",
    }
    # Response is review payload only — no tb_id / job_id.
    assert "tb_id" not in body
    assert "job_id" not in body

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        after = session.execute(
            text("SELECT COUNT(*) FROM trial_balances")
        ).scalar_one()
    assert after == before


@pytest.mark.asyncio
async def test_upload_rejects_pdf_even_when_extraction_would_succeed(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    """Bypass attempt: POST a clean PDF straight to /upload — must 400."""
    headers = auth_headers(provisioned_org["token"])
    pdf = _clean_tb_pdf()
    # Prove extraction would have worked (same bytes).
    extract = await api_client.post(
        "/trial-balances/extract-pdf",
        files={"file": ("clean-tb.pdf", BytesIO(pdf), "application/pdf")},
        headers=headers,
    )
    assert extract.status_code == 200, extract.text
    assert len(extract.json()["rows"]) >= 7

    upload = await api_client.post(
        "/trial-balances/upload",
        data={
            "company_id": str(provisioned_org["company_id"]),
            "period_end": "2025-12-31",
            "currency": "GBP",
        },
        files={"file": ("clean-tb.pdf", BytesIO(pdf), "application/pdf")},
        headers=headers,
    )
    assert upload.status_code == 400, upload.text
    assert "xlsx" in upload.json()["detail"].lower() or "csv" in upload.json()[
        "detail"
    ].lower()

    with SyncSessionLocal() as session:
        set_rls_org_id(session, provisioned_org["org_id"])
        # No TB created for this period from the rejected PDF.
        count = session.execute(
            text(
                "SELECT COUNT(*) FROM trial_balances "
                "WHERE company_id = :cid AND period_end = DATE '2025-12-31'"
            ),
            {"cid": str(provisioned_org["company_id"])},
        ).scalar_one()
    assert count == 0
