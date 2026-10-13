"""QA review fixture. The company is fictional. Figures stay the engine's."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.company import Company
from app.services.company_details import blocks_final, company_detail_checks
from app.services.reconciliation import ReconciliationCheck
from findraft.models.year_end import YearEnd
from tests.conftest import auth_headers
from tests.test_adopted_trial_balance import (
    _answer_all_no,
    _draft_version,
    _insert_tb,
    _set_file_hash,
)
from tests.test_small_adopted_finalise import _ADMIN, _SMALL, _set_statutory

_PACK = Path(__file__).resolve().parents[2] / (
    "findraft/content/frs102-1a-ie/2024.09/pack.json"
)
_NAME = "The company name does not end with Limited, Ltd, Teoranta, or Teo."
_EARLIER = (
    "This period starts after the date of incorporation. "
    "An earlier financial period must exist."
)
_OFFICE = (
    "The registered office does not look like an Irish address. "
    "No Eircode and no Irish county were found."
)
_NUMBER = "Company number '1111' is not 5 to 7 digits."
_APPOINTMENT = (
    "Director appointment is after incorporation on 7 May 2025 and no earlier "
    "director is recorded: warren buffett (3 July 2025)."
)
_SPELLING = (
    "Director 'warren buffett' is all in lowercase. Director 'warren buffett' "
    "differs by one letter from the company secretary 'Warren Buffet'. "
    "Check the spelling."
)
_EMPLOYEES = "Average employees are 677, which is above 50. Check this figure."
_PER_HEAD = (
    "Turnover per employee is below 2,000. "
    "Check the employee count against turnover."
)
_TAX = (
    "There is a profit before tax and no tax charge or corporation tax "
    "creditor. Check whether tax should be recorded."
)
_EVENTS = (
    "The question about events after the balance sheet date has not been answered."
)


def _company(**overrides: object) -> Company:
    values: dict[str, object] = {
        "client_id": uuid.uuid4(),
        "org_id": uuid.uuid4(),
        "name": "charlie mungar buffett",
        "registered_office": "New York, Ireland",
        "company_number": "1111",
        "incorporated_on": date(2025, 5, 7),
        "secretary": "Warren Buffet",
        "average_employees": 677,
        "functional_currency": "EUR",
        "country_of_incorporation": "IE",
        "directors": [
            {"name": "warren buffett", "appointed_on": "2025-07-03"},
        ],
    }
    values.update(overrides)
    return Company(**values)  # type: ignore[arg-type]


def _year(company: Company, **overrides: object) -> YearEnd:
    values: dict[str, object] = {
        "org_id": company.org_id,
        "company_id": company.id,
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 12, 31),
        "first_financial_period": True,
        "pack_id": "frs102-1a-ie",
        "pack_version": "2024.09",
    }
    values.update(overrides)
    return YearEnd(**values)  # type: ignore[arg-type]


def _by_code(
    company: Company,
    year_end: YearEnd,
    **figures: object,
) -> dict[str, ReconciliationCheck]:
    rows = company_detail_checks(
        company,
        year_end,
        turnover=figures.get("turnover", Decimal("100000.00")),  # type: ignore[arg-type]
        profit_before_tax=figures.get("profit_before_tax", Decimal("25000.00")),  # type: ignore[arg-type]
        tax_charge=figures.get("tax_charge", Decimal("0.00")),  # type: ignore[arg-type]
        corporation_tax=figures.get("corporation_tax", Decimal("0.00")),  # type: ignore[arg-type]
        subsequent_events_answered=figures.get("subsequent_events_answered", False),  # type: ignore[arg-type]
    )
    return {item.code: item for item in rows}


def test_pack_data_checks_are_reviewer_to_confirm() -> None:
    payload = json.loads(_PACK.read_text(encoding="utf-8"))
    rules = payload["data_checks"]
    assert rules["source_status"] == "reviewer-to-confirm"
    assert rules["legal_form_suffixes"] == ["Limited", "Ltd", "Teoranta", "Teo"]
    forms = payload["company_legal_forms"]
    assert forms["source_status"] == "researched (public source)"
    assert [item["code"] for item in forms["forms"]] == [
        "ltd",
        "dac",
        "plc",
        "clg",
        "ulc",
        "puc",
        "pulc",
    ]
    assert forms["forms"][0]["suffixes"] == rules["legal_form_suffixes"]
    assert forms["forms"][1]["missing_suffix"] == "notice"
    signatures = payload["board_signatures"]
    assert signatures["source_status"] == "researched (public source)"
    assert signatures["directors_report_provision"] == (
        "Companies Act 2014, section 324"
    )
    items = payload["directors_report_items"]
    assert items["source_status"] == "researched (public source)"
    assert items["dividends"] == "Companies Act 2014, section 326(1)(d)"
    assert items["share_interests"] == "Companies Act 2014, section 329"
    assert items["subsequent_year_length"] == "Companies Act 2014, section 288"
    assert rules["source_status"] == "reviewer-to-confirm"
    assert signatures["balance_sheet_provision"] == "Companies Act 2014, section 332"
    assert signatures["sole_director"] == 1
    assert signatures["two_or_more_directors"] == 2
    assert rules["first_period_max_months"] == 18
    length = payload["first_period_length"]
    assert length["source_status"] == "researched (public source)"
    assert length["provision"] == "Companies Act 2014, section 288(1)"
    assert length["max_months"] == 18
    assert rules["company_number_min_digits"] == 5
    assert rules["company_number_max_digits"] == 7
    assert rules["employee_notice_above"] == 50
    assert rules["turnover_per_employee_floor"] == "2000.00"


def test_fixture_raises_every_qa_data_check() -> None:
    company = _company()
    found = _by_code(company, _year(company))
    expected = {
        "V-CO-010": ("WARNING", _NAME),
        "V-CO-037": ("WARNING", _EARLIER),
        "V-CO-012": ("NOTICE", _OFFICE),
        "V-CO-013": ("NOTICE", _NUMBER),
        "V-CO-014": ("NOTICE", _APPOINTMENT),
        "V-CO-015": ("NOTICE", _SPELLING),
        "V-CO-016": ("NOTICE", _EMPLOYEES),
        "V-CO-017": ("NOTICE", _PER_HEAD),
        "V-CO-018": ("NOTICE", _TAX),
        "V-CO-019": ("NOTICE", _EVENTS),
    }
    for code, (severity, message) in expected.items():
        item = found[code]
        assert item.passed is False
        assert item.severity == severity
        assert item.message == message
    assert "V-CO-011" not in found
    assert blocks_final((found["V-CO-010"], found["V-CO-037"])) is True
    notices = tuple(
        found[code] for code in expected if code not in {"V-CO-010", "V-CO-037"}
    )
    assert blocks_final(notices) is False


def test_clean_letterhead_clears_the_data_checks() -> None:
    company = _company(
        name="Charlie Mungar Buffett Limited",
        registered_office="1 Harbour Street, Dublin",
        company_number="123456",
        incorporated_on=date(2026, 1, 1),
        secretary="Grace Hopper",
        average_employees=12,
        directors=[{"name": "Warren Buffett", "appointed_on": "2026-01-01"}],
    )
    found = _by_code(
        company,
        _year(company),
        tax_charge=Decimal("100.00"),
        subsequent_events_answered=True,
    )
    assert found["V-CO-010"].passed is True
    assert found["V-CO-011"].passed is True
    for code in (
        "V-CO-012",
        "V-CO-013",
        "V-CO-014",
        "V-CO-015",
        "V-CO-016",
        "V-CO-017",
        "V-CO-018",
        "V-CO-019",
    ):
        assert code not in found


def test_suffix_period_office_and_number_boundaries() -> None:
    company = _company(name="Potato")
    assert _by_code(company, _year(company))["V-CO-010"].passed is False
    company.name = "Potato Teo"
    assert _by_code(company, _year(company))["V-CO-010"].passed is True
    company.name = "Harbour Ltd."
    assert _by_code(company, _year(company))["V-CO-010"].passed is True
    company.name = "Teoranta Holdings"
    assert _by_code(company, _year(company))["V-CO-010"].passed is False

    exact = _company(
        name="Harbour Limited",
        incorporated_on=date(2025, 5, 1),
        registered_office="1 Harbour Street, Dublin",
        company_number="1234567",
    )
    exact_year = _year(
        exact,
        period_start=date(2025, 5, 1),
        period_end=date(2026, 10, 31),
    )
    assert _by_code(exact, exact_year)["V-CO-011"].passed is True
    longer = _year(exact, period_start=date(2025, 5, 1), period_end=date(2026, 11, 1))
    length = _by_code(exact, longer)["V-CO-011"]
    assert length.passed is False
    assert length.message == (
        "This first financial period is longer than 18 months. "
        "Companies Act 2014, section 288(1)."
    )
    assert "incorporation date" not in length.message
    before = _year(exact, period_start=date(2025, 4, 1), period_end=date(2025, 12, 31))
    started_early = _by_code(exact, before)["V-CO-011"]
    assert started_early.passed is False
    assert "has to start on the incorporation date" in started_early.message
    assert "V-CO-037" not in _by_code(exact, before)
    both = _year(exact, period_start=date(2026, 1, 1), period_end=date(2027, 7, 2))
    both_found = _by_code(exact, both)
    assert both_found["V-CO-037"].message == _EARLIER
    assert both_found["V-CO-011"].message == (
        "This first financial period is longer than 18 months. "
        "Companies Act 2014, section 288(1)."
    )
    assert blocks_final((both_found["V-CO-037"], both_found["V-CO-011"])) is True

    missing = _company(name="Harbour Limited", incorporated_on=None)
    missing_check = _by_code(missing, _year(missing))["V-CO-011"]
    assert missing_check.passed is False
    assert missing_check.message == (
        "The date of incorporation has not been recorded. "
        "A first financial period has to start on that date."
    )
    assert missing_check.message.strip() != ""
    assert blocks_final((missing_check,))
    ordinary = _year(missing, first_financial_period=False)
    assert "V-CO-011" not in _by_code(missing, ordinary)

    other = _year(company, pack_id="frs102-1a")
    assert "V-CO-010" not in _by_code(company, other)

    ltd = _company(name="Harbour Limited", legal_form="ltd")
    assert _by_code(ltd, _year(ltd))["V-CO-010"].passed is True
    plc = _company(name="Harbour Limited", legal_form="plc")
    plc_check = _by_code(plc, _year(plc))["V-CO-010"]
    assert plc_check.passed is False
    assert "public limited company" in plc_check.message
    assert blocks_final((plc_check,)) is True
    named = _company(name="Harbour public limited company", legal_form="plc")
    assert _by_code(named, _year(named))["V-CO-010"].passed is True

    dac = _company(
        name="Harbour Limited",
        legal_form="dac",
        directors=[{"name": "Ada Lovelace"}],
    )
    dac_found = _by_code(dac, _year(dac))
    assert "V-CO-010" not in dac_found
    assert dac_found["V-CO-025"].severity == "NOTICE"
    assert dac_found["V-CO-025"].passed is False
    assert "section 971" in dac_found["V-CO-025"].message
    assert dac_found["V-CO-026"].passed is False
    assert "section 985" in dac_found["V-CO-026"].message
    assert blocks_final((dac_found["V-CO-025"], dac_found["V-CO-026"])) is False
    suffixed = _company(
        name="Harbour Designated Activity Company",
        legal_form="dac",
        directors=[
            {"name": "Ada Lovelace"},
            {"name": "Grace Hopper", "resigned_on": "2026-06-01"},
            {"name": "Katherine Johnson"},
        ],
    )
    suffixed_found = _by_code(suffixed, _year(suffixed))
    assert suffixed_found["V-CO-010"].passed is True
    assert "V-CO-025" not in suffixed_found
    assert "V-CO-026" not in suffixed_found

    dublin = _company(registered_office="1 Harbour Street, Dublin")
    cork = _company(registered_office="Co. Cork")
    eircode = _company(registered_office="D02 AF30")
    ohio = _company(registered_office="Dublin, Ohio")
    screw = _company(registered_office="Corkscrew Lane, Ireland")
    assert "V-CO-012" not in _by_code(dublin, _year(dublin))
    assert "V-CO-012" not in _by_code(cork, _year(cork))
    assert "V-CO-012" not in _by_code(eircode, _year(eircode))
    # "Dublin" is a county word, so Dublin, Ohio passes this check.
    assert "V-CO-012" not in _by_code(ohio, _year(ohio))
    assert _by_code(screw, _year(screw))["V-CO-012"].message == _OFFICE

    short = _company(company_number="1234")
    long_number = _company(company_number="12345678")
    letters = _company(company_number="AB123456")
    assert "not 5 to 7 digits" in _by_code(short, _year(short))["V-CO-013"].message
    assert "V-CO-013" in _by_code(long_number, _year(long_number))
    assert "V-CO-013" in _by_code(letters, _year(letters))
    spaced = _company(company_number="123 456")
    assert "V-CO-013" not in _by_code(spaced, _year(spaced))


def test_missing_incorporation_date_links_to_company_details() -> None:
    """A blank date is a sentence and a Fix link, not an empty check."""
    from app.services.dashboard_groups import present_check
    from app.services.draft_workflow import Dashboard, _dashboard_dict

    company = _company(name="Harbour Limited", incorporated_on=None)
    check = _by_code(company, _year(company))["V-CO-011"]
    board = Dashboard(
        draft_id=uuid.uuid4(),
        status="draft",
        row_version=1,
        traffic="red",
        can_finalise=False,
        checks=(check,),
        unanswered_disclosures=(),
        carried_disclosures=(),
    )
    shown = _dashboard_dict(board)["checks"]
    assert isinstance(shown, list) and len(shown) == 1
    row = shown[0]
    assert row["code"] == "V-CO-011"
    assert row["passed"] is False
    assert row["message"] == (
        "The date of incorporation has not been recorded. "
        "A first financial period has to start on that date."
    )
    assert row["area"] == "Company details"
    fix = row["fix"]
    assert isinstance(fix, dict)
    assert fix["section"] == "company-details"
    linked = present_check("V-CO-011")
    assert linked.area == "Company details"
    assert linked.fix.section == "company-details"


def test_names_employees_tax_and_events_boundaries() -> None:
    titled = _company(
        secretary="Grace Hopper",
        directors=[{"name": "Ada Lovelace", "appointed_on": "2025-05-07"}],
        average_employees=50,
    )
    found = _by_code(titled, _year(titled), turnover=Decimal("100000.00"))
    assert "V-CO-014" not in found
    assert "V-CO-015" not in found
    assert "V-CO-016" not in found
    assert "V-CO-017" not in found

    earlier = _company(
        directors=[
            {"name": "Ada Lovelace", "appointed_on": "2025-05-01"},
            {"name": "warren buffett", "appointed_on": "2025-07-03"},
        ]
    )
    assert "V-CO-014" not in _by_code(earlier, _year(earlier))
    undated = _company(directors=[{"name": "Ada Lovelace"}])
    assert "V-CO-014" not in _by_code(undated, _year(undated))

    low = _company(average_employees=51)
    assert "above 50" in _by_code(low, _year(low), turnover=None)["V-CO-016"].message
    assert "V-CO-017" not in _by_code(low, _year(low), turnover=None)
    exact = _company(average_employees=10)
    at_floor = _by_code(exact, _year(exact), turnover=Decimal("20000.00"))
    assert "V-CO-017" not in at_floor
    under = _by_code(exact, _year(exact), turnover=Decimal("19999.99"))
    assert under["V-CO-017"].passed is False

    loss = _by_code(
        _company(average_employees=None),
        _year(_company()),
        profit_before_tax=Decimal("-10.00"),
    )
    assert "V-CO-016" not in loss
    assert "V-CO-018" not in loss
    charged = _by_code(_company(), _year(_company()), tax_charge=Decimal("1.00"))
    assert "V-CO-018" not in charged
    creditor = _by_code(_company(), _year(_company()), corporation_tax=Decimal("-1.00"))
    assert "V-CO-018" not in creditor
    answered = _by_code(_company(), _year(_company()), subsequent_events_answered=True)
    assert "V-CO-019" not in answered
    unknown = _by_code(_company(), _year(_company()), subsequent_events_answered=None)
    assert "V-CO-019" not in unknown


@pytest.mark.asyncio
async def test_fixture_dashboard_blocks_final_and_links_each_check(
    api_client: AsyncClient,
    provisioned_org: dict,
) -> None:
    org_id = provisioned_org["org_id"]
    company_id = provisioned_org["company_id"]
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        session.execute(
            text(
                "UPDATE companies SET name = :name, functional_currency = 'EUR' "
                "WHERE id = :id"
            ),
            {"name": "charlie mungar buffett", "id": str(company_id)},
        )
        session.execute(
            text("UPDATE organisations SET name = :name WHERE id = :id"),
            {"name": "kastree's Organization", "id": str(org_id)},
        )
        session.commit()
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=_SMALL,
        period_start=date(2026, 1, 1),
    )
    _set_file_hash(tb_id, org_id, "cd" * 32)
    _set_statutory(org_id=org_id, company_id=company_id, lines=_ADMIN)
    headers = auth_headers(provisioned_org["token"])
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    period = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert period.status_code == 200, period.text
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/company-details",
        headers=headers,
        json={
            "registered_office": "New York, Ireland",
            "company_number": "1111",
            "incorporated_on": "2025-05-07",
            "principal_activity": "Investing",
            "secretary": "Warren Buffet",
            "average_employees": 677,
            "directors": [
                {"name": "warren buffett", "appointed_on": "2025-07-03"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    approved = await api_client.put(
        f"/year-ends/{year_end_id}/approval",
        headers=headers,
        json={
            "approval_date": "2027-03-15",
            "signing_directors": ["warren buffett"],
        },
    )
    assert approved.status_code == 200, approved.text
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    draft_id = draft.json()["draft_id"]
    board = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert board.status_code == 200, board.text
    body = board.json()
    assert body["can_finalise"] is False
    checks = {item["code"]: item for item in body["checks"]}
    expected_fix = {
        "V-CO-010": ("company-details", _NAME),
        "V-CO-037": ("review", _EARLIER),
        "V-CO-012": ("company-details", _OFFICE),
        "V-CO-013": ("company-details", _NUMBER),
        "V-CO-014": ("company-details", _APPOINTMENT),
        "V-CO-015": ("company-details", _SPELLING),
        "V-CO-016": ("company-details", _EMPLOYEES),
        "V-CO-017": ("company-details", _PER_HEAD),
        "V-CO-018": ("income", _TAX),
        "V-CO-019": ("disclosures", _EVENTS),
    }
    for code, (section, message) in expected_fix.items():
        item = checks[code]
        assert item["passed"] is False
        assert item["message"] == message
        assert item["fix"]["section"] == section
    statements = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert statements.status_code == 200, statements.text
    assert statements.json()["profit"] == "25000.00"
    assert statements.json()["net_assets"] == "35000.00"
    _answer_all_no(org_id=org_id, company_id=company_id, draft_id=draft_id)
    cleared = await api_client.get(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/dashboard",
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    after = {item["code"]: item for item in cleared.json()["checks"]}
    assert "V-CO-019" not in after
    assert cleared.json()["can_finalise"] is False
    refused = await api_client.post(
        f"/year-ends/{year_end_id}/drafts/{draft_id}/finalise",
        headers={**headers, "Idempotency-Key": "qa-fixture-finalise"},
        json={"row_version": _draft_version(draft_id, org_id)},
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == _NAME
