"""GET /health reports the Alembic revision and still returns 200."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.schema_revision import schema_revision


def test_one_matching_head_is_a_match() -> None:
    status = schema_revision(database=("l8m9n0o1p2",), heads=("l8m9n0o1p2",))
    assert status.revision_matches is True
    assert status.database_revision == "l8m9n0o1p2"
    assert status.code_revision == "l8m9n0o1p2"


def test_a_different_database_revision_does_not_match() -> None:
    status = schema_revision(database=("k7l8m9n0o1",), heads=("l8m9n0o1p2",))
    assert status.revision_matches is False
    assert status.database_revision == "k7l8m9n0o1"
    assert status.code_revision == "l8m9n0o1p2"


def test_an_unreadable_database_does_not_match() -> None:
    status = schema_revision(database=None, heads=("l8m9n0o1p2",))
    assert status.revision_matches is False
    assert status.database_revision is None
    assert status.code_revision == "l8m9n0o1p2"


@pytest.mark.asyncio
async def test_health_stays_ok_when_the_revision_cannot_be_read(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unread() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "app.services.schema_revision.database_revisions", unread
    )
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["revision_matches"] is False
    assert body["database_revision"] is None
    assert "git_sha" in body


@pytest.mark.asyncio
async def test_health_reports_the_live_revision(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["revision_matches"] is True
    assert body["database_revision"] == body["code_revision"]
    assert isinstance(body["code_revision"], str)
    assert body["code_revision"]
