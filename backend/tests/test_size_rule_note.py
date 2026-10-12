"""Size message when two of three pass and a condition still fails."""

from __future__ import annotations

from decimal import Decimal

from app.services.size_eligibility import YearSize, assess_size
from findraft.engine.pack import load_manifest, pack_dir

_NOTE = (
    "A reviewer must confirm whether the audit exemption is available "
    "(two of three versus all conditions)."
)


def _manifest() -> dict[str, object]:
    loaded: object = load_manifest(pack_dir("frs102-1a-ie", "2024.09") / "pack.json")
    assert isinstance(loaded, dict)
    return loaded


def test_qa_fixture_names_the_failed_employee_condition() -> None:
    manifest = _manifest()
    note = manifest["size_rule_note"]
    assert isinstance(note, dict)
    assert note["source_status"] == "reviewer-to-confirm"
    assert note["text"] == _NOTE
    assessment = assess_size(
        manifest,
        company_currency="EUR",
        current=YearSize(
            turnover=Decimal("100000.00"),
            balance_sheet_total=Decimal("35000.00"),
            employees=677,
        ),
        preceding=None,
        first_financial_period=True,
    )
    assert assessment.eligible is True
    assert assessment.current_conditions_met == 2
    assert assessment.preceding_conditions_met is None
    assert assessment.message == (
        "Current year: turnover met; balance sheet total met; employees not met. "
        "This year end is a first financial period, so there is no preceding year. "
        f"{_NOTE}"
    )
    assert "eligible" not in assessment.message.casefold()


def test_all_three_met_omits_the_reviewer_sentence() -> None:
    assessment = assess_size(
        _manifest(),
        company_currency="EUR",
        current=YearSize(
            turnover=Decimal("100000.00"),
            balance_sheet_total=Decimal("35000.00"),
            employees=10,
        ),
        preceding=None,
        first_financial_period=True,
    )
    assert assessment.eligible is True
    assert assessment.message == (
        "Current year: turnover met; balance sheet total met; employees met. "
        "This year end is a first financial period, so there is no preceding year."
    )
    assert "eligible" not in assessment.message.casefold()
