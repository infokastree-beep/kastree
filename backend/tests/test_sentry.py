"""Sentry bootstrap and gated debug endpoint."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_sentry_debug_404_when_token_unset(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.settings.sentry_debug_token", None)
    response = await api_client.get("/sentry-debug", params={"token": "anything"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sentry_debug_404_when_token_wrong(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.settings.sentry_debug_token", "expected-token")
    response = await api_client.get("/sentry-debug", params={"token": "wrong"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sentry_debug_raises_when_token_matches(
    api_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.settings.sentry_debug_token", "expected-token")
    with pytest.raises(RuntimeError, match="Sentry deliberate test error"):
        await api_client.get("/sentry-debug", params={"token": "expected-token"})


def test_init_sentry_noop_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import sentry_setup

    monkeypatch.setattr(sentry_setup.settings, "sentry_dsn", None)
    assert sentry_setup.init_sentry() is False


def test_init_sentry_calls_sdk_when_dsn_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import sentry_setup

    called: dict[str, object] = {}

    def _fake_init(**kwargs: object) -> None:
        called.update(kwargs)

    monkeypatch.setattr(sentry_setup.settings, "sentry_dsn", "https://key@o0.ingest.sentry.io/1")
    monkeypatch.setattr(sentry_setup.settings, "app_env", "production")
    monkeypatch.setattr(sentry_setup.settings, "app_version", "0.1.0")
    monkeypatch.setattr(sentry_setup.sentry_sdk, "init", _fake_init)

    assert sentry_setup.init_sentry() is True
    assert called["dsn"] == "https://key@o0.ingest.sentry.io/1"
    assert called["environment"] == "production"
    assert called["send_default_pii"] is False
    assert called["traces_sample_rate"] == 0.05
