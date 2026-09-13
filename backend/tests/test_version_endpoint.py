"""Deployed-revision endpoints: GET /health (git_sha field) and GET /version."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.config import settings


@pytest.mark.asyncio
async def test_health_includes_status_and_git_sha(api_client: AsyncClient) -> None:
    resp = await api_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "git_sha" in body


@pytest.mark.asyncio
async def test_version_returns_app_version_and_git_sha(api_client: AsyncClient) -> None:
    resp = await api_client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == settings.app_version
    assert "git_sha" in body


@pytest.mark.asyncio
async def test_health_reports_baked_git_sha(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build-baked GIT_SHA is surfaced verbatim on /health and /version."""
    monkeypatch.setattr(settings, "git_sha", "abc1234def")
    monkeypatch.setattr(settings, "railway_git_commit_sha", None)
    health = await api_client.get("/health")
    version = await api_client.get("/version")
    assert health.json()["git_sha"] == "abc1234def"
    assert version.json()["git_sha"] == "abc1234def"


@pytest.mark.asyncio
async def test_git_sha_falls_back_to_railway_then_unknown(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Precedence: GIT_SHA (build) -> RAILWAY_GIT_COMMIT_SHA (runtime) -> 'unknown'."""
    # Empty/placeholder build value falls through to the Railway runtime value.
    monkeypatch.setattr(settings, "git_sha", "")
    monkeypatch.setattr(settings, "railway_git_commit_sha", "railwaysha99")
    assert (await api_client.get("/version")).json()["git_sha"] == "railwaysha99"

    # Neither set -> unknown (never raises).
    monkeypatch.setattr(settings, "git_sha", None)
    monkeypatch.setattr(settings, "railway_git_commit_sha", None)
    assert (await api_client.get("/version")).json()["git_sha"] == "unknown"
