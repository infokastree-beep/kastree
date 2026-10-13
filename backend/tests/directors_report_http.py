"""A recorded nil directors' report, so an existing finalise path stays complete."""

from __future__ import annotations

from httpx import AsyncClient


def nil_directors_report(
    *,
    directors: list[str],
    secretary: str | None = None,
) -> dict[str, object]:
    people: list[dict[str, object]] = [
        {
            "name": name,
            "role": "director",
            "at_start": {"interested": False, "holdings": []},
            "at_end": {"interested": False, "holdings": []},
        }
        for name in directors
    ]
    if secretary:
        people.append(
            {
                "name": secretary,
                "role": "secretary",
                "at_start": {"interested": False, "holdings": []},
                "at_end": {"interested": False, "holdings": []},
            }
        )
    return {
        "accounting_records_location": "1 Harbour Street, Dublin",
        "interim_dividend": "0.00",
        "recommended_dividend": "0.00",
        "share_interests": people,
        "research_development_relevant": False,
        "political_donations_relevant": False,
    }


async def save_nil_directors_report(
    api_client: AsyncClient,
    headers: dict[str, str],
    year_end_id: str,
    *,
    directors: list[str],
    secretary: str | None = None,
) -> None:
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=headers,
        json=nil_directors_report(directors=directors, secretary=secretary),
    )
    assert saved.status_code == 200, saved.text
