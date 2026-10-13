"""Record the compilation date and signatory on an open year end."""

from __future__ import annotations

from httpx import AsyncClient

_DATE = "2026-03-31"
_SIGNATORY = "Pat Lee"


async def save_compilation_report(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    *,
    compilation_date: str = _DATE,
    compilation_signatory: str = _SIGNATORY,
) -> None:
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/compilation-report",
        headers=headers,
        json={
            "compilation_date": compilation_date,
            "compilation_signatory": compilation_signatory,
        },
    )
    assert saved.status_code == 200, saved.text
