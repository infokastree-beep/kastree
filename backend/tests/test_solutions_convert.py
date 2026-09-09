"""Public Kastree Convert — extract, checkout, download (no auth)."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from weasyprint import HTML

from app.main import app
from app.services.rate_limit import reset_rate_limits_for_tests
from app.services.standalone_convert import (
    load_conversion_by_session,
    mark_paid_by_session,
    save_conversion,
    update_conversion,
)


def _tb_pdf() -> bytes:
    html = """
    <html><body><table border="1">
      <tr><th>Account Code</th><th>Account Name</th><th>Debit</th><th>Credit</th></tr>
      <tr><td>1000</td><td>Bank</td><td>1000.00</td><td>0.00</td></tr>
      <tr><td>1100</td><td>AR</td><td>500.00</td><td>0.00</td></tr>
      <tr><td>2000</td><td>AP</td><td>0.00</td><td>300.00</td></tr>
      <tr><td>3000</td><td>Capital</td><td>0.00</td><td>1200.00</td></tr>
      <tr><td>4000</td><td>Sales</td><td>0.00</td><td>2000.00</td></tr>
      <tr><td>5000</td><td>COS</td><td>800.00</td><td>0.00</td></tr>
      <tr><td>6000</td><td>Opex</td><td>1200.00</td><td>0.00</td></tr>
    </table></body></html>
    """
    return HTML(string=html).write_pdf()


@pytest.fixture(autouse=True)
def _reset_limits() -> None:
    reset_rate_limits_for_tests()


@pytest.mark.asyncio
async def test_convert_extract_public_no_auth() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/solutions/convert/extract",
            files={"file": ("tb.pdf", BytesIO(_tb_pdf()), "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["rows"]) >= 7
    assert "tb_id" not in body


@pytest.mark.asyncio
async def test_convert_download_requires_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.routers.solutions.settings.stripe_secret_key",
        "sk_test_dummy",
    )
    rows = [
        {
            "account_code": "1000",
            "account_name": "Bank",
            "debit": "100.00",
            "credit": "0.00",
        }
    ]
    conversion_id = save_conversion(rows=rows)
    update_conversion(conversion_id, stripe_session_id="cs_test_unpaid")

    transport = ASGITransport(app=app)
    with patch("app.routers.solutions.stripe") as stripe_mod:
        class FakeSession(dict):
            pass

        fake = FakeSession(payment_status="unpaid", id="cs_test_unpaid")
        stripe_mod.checkout.Session.retrieve.return_value = fake
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/solutions/convert/download",
                params={"session_id": "cs_test_unpaid"},
            )
    assert resp.status_code == 402, resp.text


@pytest.mark.asyncio
async def test_convert_download_after_paid() -> None:
    rows = [
        {
            "account_code": "1000",
            "account_name": "Bank",
            "debit": "100.00",
            "credit": "0.00",
        },
        {
            "account_code": "2000",
            "account_name": "AP",
            "debit": "0.00",
            "credit": "100.00",
        },
    ]
    conversion_id = save_conversion(rows=rows)
    update_conversion(conversion_id, stripe_session_id="cs_test_paid_ok")
    mark_paid_by_session("cs_test_paid_ok")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/solutions/convert/download",
            params={"session_id": "cs_test_paid_ok"},
        )
    assert resp.status_code == 200, resp.text
    assert "spreadsheetml" in resp.headers.get("content-type", "")
    assert resp.content[:2] == b"PK"  # xlsx zip magic


@pytest.mark.asyncio
async def test_convert_checkout_creates_payment_mode_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.routers.solutions.settings.stripe_secret_key",
        "sk_test_dummy",
    )
    monkeypatch.setattr(
        "app.routers.solutions.settings.stripe_price_id_convert",
        "price_test_convert",
    )
    monkeypatch.setattr(
        "app.routers.solutions.settings.frontend_base_url",
        "http://127.0.0.1:43123",
    )

    created: dict = {}

    def fake_create(**kwargs):  # type: ignore[no-untyped-def]
        created.update(kwargs)
        return {"id": "cs_test_new", "url": "https://checkout.stripe.com/test"}

    transport = ASGITransport(app=app)
    with patch("app.routers.solutions.stripe") as stripe_mod:
        stripe_mod.checkout.Session.create.side_effect = fake_create
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/solutions/convert/checkout",
                json={
                    "rows": [
                        {
                            "account_code": "1000",
                            "account_name": "Bank",
                            "debit": "10.00",
                            "credit": "0",
                        }
                    ],
                    "customer_email": "a@example.com",
                },
            )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com")
    assert created.get("mode") == "payment"
    assert created["metadata"]["product"] == "kastree_convert"
    job = load_conversion_by_session("cs_test_new")
    assert job is not None
    assert job["status"] == "pending_payment"
