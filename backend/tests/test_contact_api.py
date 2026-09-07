"""Public POST /contact — rate limit + Resend founder forward."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_contact_sends_when_resend_ok() -> None:
    with patch(
        "app.routers.contact.notify_founder_contact_message",
        return_value=True,
    ) as mock_notify:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/contact",
                json={
                    "name": "Ada",
                    "email": "ada@example.com",
                    "message": "Interested in Growth for 20 clients.",
                },
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}
    mock_notify.assert_called_once()
    kwargs = mock_notify.call_args.kwargs
    assert kwargs["name"] == "Ada"
    assert kwargs["email"] == "ada@example.com"
    assert "Growth" in kwargs["message"]


@pytest.mark.asyncio
async def test_contact_503_when_email_not_delivered() -> None:
    with patch(
        "app.routers.contact.notify_founder_contact_message",
        return_value=False,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/contact",
                json={
                    "name": "Ada",
                    "email": "ada@example.com",
                    "message": "Hello",
                },
            )
    assert resp.status_code == 503
