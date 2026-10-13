"""Directors' report facts block FINAL when required and print as placeholders.

Companies Act 2014, sections 326, 328 and 329. A business review stays
optional. The later-year length check is a notice. Golden figures stay put.
"""

from __future__ import annotations

import html
import json
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.company import Company
from app.schemas.company_details import CompanyDetailsResponse
from app.services.company_data_checks import company_data_checks
from app.services.company_details import blocks_final
from app.services.directors_report import (
    directors_report_checks,
    directors_report_paragraphs,
)
from app.services.statutory_compose import compose_year_end_pdf, extract_section_html
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd
from tests.conftest import auth_headers
from tests.test_organisations_api import _add_org_user
from tests.test_statutory_statements import _golden

_FORBIDDEN = "You don't have permission to access this resource."
_FINAL = "This draft is final. It cannot be changed."
_LOCKED = "This draft is locked. It cannot be changed."
_FROZEN = "This draft is frozen. It cannot be changed."
_LOCATION = "[accounting records location not recorded]"
_INTERIM = "[interim dividend not recorded]"
_RECOMMENDED = "[recommended dividend not recorded]"
_INTERESTS = "[directors' and secretary's interests in shares not recorded]"
_OWN = "[own shares particulars not recorded]"
_EVENTS = "[subsequent events not recorded]"
_RESEARCH = "[research and development particulars not recorded]"
_POLITICAL = "[political donations particulars not recorded]"


def _print_role() -> None:
    with SyncSessionLocal() as session:
        role = session.execute(text("SELECT current_user")).scalar_one()
    print(f"executing_role={role}", flush=True)
    assert role == "findraft"


def _company(**overrides: object) -> Company:
    values: dict[str, object] = {
        "org_id": uuid.uuid4(),
        "client_id": uuid.uuid4(),
        "name": "Harbour Limited",
        "functional_currency": "EUR",
        "directors": [{"name": "Ada Lovelace"}],
        "secretary": "Grace Hopper",
        "principal_activity": "Software",
    }
    values.update(overrides)
    return Company(**values)


def _year(**overrides: object) -> YearEnd:
    values: dict[str, object] = {
        "org_id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "period_start": date(2025, 1, 1),
        "period_end": date(2025, 12, 31),
        "pack_id": "frs102-1a-ie",
        "pack_version": "2024.09",
        "first_financial_period": False,
    }
    values.update(overrides)
    return YearEnd(**values)


def _nil_interest(name: str, role: str = "director") -> dict[str, object]:
    end = {"interested": False, "holdings": []}
    return {"name": name, "role": role, "at_start": end, "at_end": end}


def _complete(year_end: YearEnd) -> None:
    year_end.accounting_records_location = "1 Harbour Street, Dublin"
    year_end.interim_dividend = Decimal("0.00")
    year_end.recommended_dividend = Decimal("0.00")
    year_end.share_interests = [
        _nil_interest("Ada Lovelace"),
        _nil_interest("Grace Hopper", "secretary"),
    ]


def _by_code(checks: tuple[object, ...]) -> dict[str, object]:
    return {str(item.code): item for item in checks}


def test_an_older_final_snapshot_still_validates_without_the_new_facts() -> None:
    stored = {
        "country_of_incorporation": "IE",
        "registered_office": "1 Harbour Road",
        "business_address": None,
        "company_number": "123456",
        "incorporated_on": None,
        "principal_activity": None,
        "secretary": None,
        "average_employees": None,
        "directors": [],
        "advisers": [],
        "share_classes": [],
        "approval_date": None,
        "signing_directors": [],
    }
    parsed = CompanyDetailsResponse.model_validate(stored)
    assert parsed.accounting_records_location is None
    assert parsed.interim_dividend is None
    assert parsed.recommended_dividend is None
    assert parsed.share_interests == []
    assert parsed.research_development_relevant is None
    assert parsed.accounting_period_change_filed is None


def test_required_facts_block_final_and_optional_facts_do_not() -> None:
    company = _company()
    blank = _year()
    missing = directors_report_checks(company, blank)
    codes = _by_code(missing)
    for code in ("V-CO-029", "V-CO-030", "V-CO-031", "V-CO-032"):
        item = codes[code]
        assert item.passed is False
    for code in ("V-CO-033", "V-CO-034", "V-CO-035", "V-CO-036"):
        assert code not in codes
    assert blocks_final(missing) is True

    _complete(blank)
    ready = directors_report_checks(company, blank)
    assert blocks_final(ready) is False
    assert all(item.passed for item in ready)

    resigned = _company(
        directors=[
            {"name": "Ada Lovelace"},
            {"name": "Charles Babbage", "resigned_on": "2026-06-01"},
        ]
    )
    partial = directors_report_checks(resigned, blank)
    assert _by_code(partial)["V-CO-032"].passed is False
    interests = list(blank.share_interests or [])
    interests.append(_nil_interest("Charles Babbage"))
    blank.share_interests = interests
    assert _by_code(directors_report_checks(resigned, blank))["V-CO-032"].passed is True

    own = directors_report_checks(company, blank, own_shares_held=True)
    assert _by_code(own)["V-CO-033"].passed is False
    assert blocks_final(own) is True
    assert "V-CO-033" not in _by_code(
        directors_report_checks(company, blank, own_shares_held=False)
    )
    assert "V-CO-033" not in _by_code(directors_report_checks(company, blank))
    blank.own_shares_particulars = "The company holds its own shares."
    assert _by_code(
        directors_report_checks(company, blank, own_shares_held=True)
    )["V-CO-033"].passed is True

    events = directors_report_checks(company, blank, subsequent_events_yes=True)
    assert _by_code(events)["V-CO-034"].passed is False
    assert "V-CO-034" not in _by_code(
        directors_report_checks(company, blank, subsequent_events_yes=False)
    )
    blank.subsequent_events_particulars = "A contract was signed."
    assert _by_code(
        directors_report_checks(company, blank, subsequent_events_yes=True)
    )["V-CO-034"].passed is True

    blank.research_development_relevant = True
    research = directors_report_checks(company, blank)
    assert _by_code(research)["V-CO-035"].passed is False
    blank.research_development_relevant = None
    assert "V-CO-035" not in _by_code(directors_report_checks(company, blank))
    blank.research_development_relevant = False
    assert "V-CO-035" not in _by_code(directors_report_checks(company, blank))
    blank.research_development_relevant = True
    blank.research_development_detail = "New products"
    assert _by_code(directors_report_checks(company, blank))["V-CO-035"].passed is True

    blank.political_donations_relevant = True
    blank.political_donations_detail = None
    assert _by_code(directors_report_checks(company, blank))["V-CO-036"].passed is False
    blank.political_donations_relevant = None
    assert "V-CO-036" not in _by_code(directors_report_checks(company, blank))


def test_subsequent_year_length_is_a_notice() -> None:
    company = _company()

    def length(year_end: YearEnd) -> object | None:
        found = [
            item
            for item in company_data_checks(company, year_end)
            if item.code == "V-CO-027"
        ]
        assert len(found) <= 1
        return found[0] if found else None

    assert length(_year()) is None
    assert length(_year(period_end=date(2026, 1, 7))) is None
    assert length(_year(period_end=date(2025, 12, 24))) is None
    late = length(_year(period_end=date(2026, 1, 8)))
    assert late is not None
    assert late.severity == "NOTICE"
    assert late.passed is False
    assert "section 288" in late.message
    assert blocks_final((late,)) is False
    early = length(_year(period_end=date(2025, 12, 23)))
    assert early is not None
    assert early.severity == "NOTICE"
    filed = _year(period_end=date(2026, 1, 8), accounting_period_change_filed=True)
    assert length(filed) is None
    first = _year(period_end=date(2026, 1, 8), first_financial_period=True)
    assert length(first) is None
    assert length(_year(period_start=None, period_end=date(2026, 1, 8))) is None


def test_placeholders_print_on_the_directors_report_and_figures_stay() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert document.html is not None
    assert _LOCATION not in document.html
    company = _company()
    year_end = _year(
        signing_directors=["Ada Lovelace"],
        approval_date=date(2026, 3, 17),
    )
    composed = compose_year_end_pdf(document, year_end, company=company)
    section = extract_section_html(composed, "directors-report")
    assert section is not None
    section = html.unescape(section)
    for placeholder in (_LOCATION, _INTERIM, _RECOMMENDED, _INTERESTS):
        assert placeholder in section
    assert _OWN not in section
    assert _EVENTS not in section
    assert _RESEARCH not in section
    assert _POLITICAL not in section
    assert "It does not include a business review." in section
    assert section.index(_LOCATION) < section.index(
        "Approved by the board and signed on its behalf by"
    )
    assert section.count("Approved by the board and signed on its behalf by") == 1
    assert "Ada Lovelace" in section
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert "455,812" in composed
    assert "157,650" in composed

    _complete(year_end)
    year_end.interim_dividend = Decimal("1250.50")
    year_end.recommended_dividend = Decimal("-10.00")
    filled = "\n".join(
        directors_report_paragraphs(year_end, company, currency="EUR")
    )
    assert (
        "The directors have taken the measures necessary to secure compliance "
        "with sections 281 to 285 of the Companies Act 2014. "
        "The accounting records are kept at 1 Harbour Street, Dublin."
    ) in filled
    assert "An interim dividend of €1,250.50 was paid during the financial year." in filled
    assert "The directors recommend a final dividend of (€10.00)." in filled
    assert _LOCATION not in filled
    year_end.interim_dividend = Decimal("0.01")
    year_end.recommended_dividend = Decimal("0")
    nil = "\n".join(directors_report_paragraphs(year_end, company, currency="EUR"))
    assert "No interim dividend was paid during the financial year." in nil
    assert "The directors do not recommend a final dividend." in nil

    flagged = "\n".join(
        directors_report_paragraphs(
            year_end,
            company,
            currency="EUR",
            disclosure_flags={"OWN_SHARES_HELD": True, "SUBSEQUENT_EVENTS": True},
        )
    )
    assert _OWN in flagged
    assert _EVENTS in flagged
    year_end.own_shares_particulars = "Held throughout the year."
    year_end.subsequent_events_particulars = "A lease was signed."
    recorded = "\n".join(
        directors_report_paragraphs(
            year_end,
            company,
            currency="EUR",
            disclosure_flags={"OWN_SHARES_HELD": True, "SUBSEQUENT_EVENTS": True},
        )
    )
    assert "Held throughout the year." in recorded
    assert "Events since the balance sheet date: A lease was signed." in recorded
    year_end.research_development_relevant = False
    year_end.political_donations_relevant = True
    optional = "\n".join(
        directors_report_paragraphs(year_end, company, currency="EUR")
    )
    assert "No research and development information is required to be reported." in optional
    assert _POLITICAL in optional
    quiet = "\n".join(
        directors_report_paragraphs(
            _year(),
            company,
            currency="EUR",
            disclosure_flags={"OWN_SHARES_HELD": False},
        )
    )
    assert _OWN not in quiet
    assert "Research and development" not in quiet


def _set_draft(
    *,
    org_id: uuid.UUID,
    year_end_id: str,
    status: str,
    frozen: bool,
) -> None:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        updated = session.execute(
            text(
                """
                UPDATE findraft_draft_versions
                SET status = :status,
                    is_frozen = :frozen,
                    snapshot = CASE
                      WHEN :status = 'final' THEN COALESCE(snapshot, CAST('{}' AS jsonb))
                      ELSE snapshot
                    END,
                    inputs_sha256 = CASE
                      WHEN :status = 'final' THEN COALESCE(inputs_sha256, :sha)
                      ELSE inputs_sha256
                    END,
                    engine_sha = CASE
                      WHEN :status = 'final' THEN COALESCE(engine_sha, :sha)
                      ELSE engine_sha
                    END
                WHERE org_id = :org AND year_end_id = :year_end
                """
            ),
            {
                "status": status,
                "frozen": frozen,
                "org": str(org_id),
                "year_end": year_end_id,
                "sha": "a" * 64,
            },
        )
        assert updated.rowcount == 1
        session.commit()


@pytest.mark.asyncio
async def test_a_member_saves_the_directors_report_and_a_closed_draft_refuses(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    _print_role()
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        f"/clients/{provisioned_org['client_id']}/companies",
        headers=headers,
        json={"name": "Harbour Trading Limited"},
    )
    assert created.status_code == 201, created.text
    company_id = created.json()["id"]
    opened = await api_client.post(
        "/year-ends",
        headers=headers,
        json={
            "company_id": company_id,
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
        },
    )
    assert opened.status_code == 201, opened.text
    year_end_id = opened.json()["id"]
    loaded = await api_client.get(f"/year-ends/{year_end_id}", headers=headers)
    assert loaded.status_code == 200, loaded.text
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            DraftVersion(
                org_id=org_id,
                company_id=uuid.UUID(company_id),
                year_end_id=uuid.UUID(year_end_id),
                version_number=1,
                pack_id=loaded.json()["pack_id"],
                pack_version=loaded.json()["pack_version"],
                status="draft",
                is_frozen=False,
            )
        )
        session.commit()

    member_id, _clerk, member_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="directors-report-member",
    )
    member_headers = auth_headers(member_token)
    _viewer_id, _viewer_clerk, viewer_token = _add_org_user(
        org_id=org_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="viewer",
        email_prefix="directors-report-viewer",
    )
    body = {
        "accounting_records_location": "1 Harbour Street, Dublin",
        "interim_dividend": "1,250.50",
        "recommended_dividend": "(10.00)",
        "share_interests": [
            {
                "name": "Ada Lovelace",
                "role": "director",
                "at_start": {
                    "interested": True,
                    "holdings": [
                        {
                            "undertaking": "Harbour Trading Limited",
                            "shares": 100,
                            "amount": "99.00",
                        }
                    ],
                },
                "at_end": {"interested": False, "holdings": []},
            }
        ],
        "research_development_relevant": False,
        "political_donations_relevant": None,
    }
    refused = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=auth_headers(viewer_token),
        json=body,
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"] == _FORBIDDEN

    cents = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=member_headers,
        json={**body, "interim_dividend": "1.001"},
    )
    assert cents.status_code == 400, cents.text
    assert cents.json()["detail"] == "Interim dividend must be in cents."

    saved = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=member_headers,
        json=body,
    )
    assert saved.status_code == 200, saved.text
    payload = saved.json()
    assert payload["interim_dividend"] == "1250.50"
    assert payload["recommended_dividend"] == "-10.00"
    assert payload["accounting_records_location"] == "1 Harbour Street, Dublin"
    assert payload["share_interests"][0]["at_start"]["holdings"][0]["amount"] == "99.00"
    assert isinstance(member_id, uuid.UUID)

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text(
                """
                SELECT user_id::text, entity_type, old_value, new_value
                FROM audit_logs
                WHERE org_id = :org AND action = 'directors_report_saved'
                  AND entity_id = :year_end
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"org": str(org_id), "year_end": year_end_id},
        ).one()
    assert row.user_id == str(member_id)
    assert row.entity_type == "year_end"
    recorded = json.dumps({"old": row.old_value, "new": row.new_value})
    assert "1250.50" not in recorded
    assert "1,250.50" not in recorded
    assert "99.00" not in recorded
    assert "-10.00" not in recorded
    assert row.new_value["interim_dividend_recorded"] is True
    assert row.new_value["recommended_dividend_recorded"] is True
    assert row.new_value["accounting_records_location"] == "1 Harbour Street, Dublin"
    assert row.new_value["share_interests"] == [
        {
            "name": "Ada Lovelace",
            "role": "director",
            "at_start_interested": True,
            "at_end_interested": False,
        }
    ]

    _set_draft(org_id=org_id, year_end_id=year_end_id, status="locked", frozen=False)
    locked = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=member_headers,
        json=body,
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"] == _LOCKED

    _set_draft(org_id=org_id, year_end_id=year_end_id, status="final", frozen=False)
    final = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=member_headers,
        json=body,
    )
    assert final.status_code == 409, final.text
    assert final.json()["detail"] == _FINAL

    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.add(
            DraftVersion(
                org_id=org_id,
                company_id=uuid.UUID(company_id),
                year_end_id=uuid.UUID(year_end_id),
                version_number=2,
                pack_id=loaded.json()["pack_id"],
                pack_version=loaded.json()["pack_version"],
                status="draft",
                is_frozen=True,
            )
        )
        session.commit()
    frozen = await api_client.put(
        f"/year-ends/{year_end_id}/directors-report",
        headers=member_headers,
        json=body,
    )
    assert frozen.status_code == 409, frozen.text
    assert frozen.json()["detail"] == _FROZEN
