"""Word-boundary sub-line suggestions for the seven ambiguous Product 1 lines."""

from __future__ import annotations

from decimal import Decimal

from app.services.statutory_sublines import allowed_sublines, suggest_subline
from findraft.engine.statements import build_income_statement, prior_from_mapped


def _hit(product1: str, name: str) -> tuple[str | None, int | None]:
    suggestion = suggest_subline(product1, name)
    if suggestion is None:
        return None, None
    return suggestion.engine_line, suggestion.score


def test_word_boundaries_do_not_match_inside_another_word() -> None:
    assert _hit("property_plant_equipment", "Landlord") == (None, None)
    assert _hit("property_plant_equipment", "Motorway") == (None, None)
    assert _hit("property_plant_equipment", "Plantation") == (None, None)
    assert _hit("operating_expenses", "Current account") == (None, None)
    assert _hit("intangible_assets", "Amorphous") == (None, None)


def test_confident_names_suggest_and_generic_names_stay_empty() -> None:
    cases = (
        ("property_plant_equipment", "Motor Vehicles - Cost", "FA_MOTOR_COST", 40),
        ("property_plant_equipment", "Plant & machinery - cost", "FA_PLANT_COST", 35),
        ("property_plant_equipment", "Accumulated depreciation - plant", "FA_ACCUM_DEP", 40),
        ("property_plant_equipment", "Office Equipment", None, None),
        ("property_plant_equipment", "Equipment", None, None),
        ("property_plant_equipment", "Leasehold improvements", None, None),
        ("operating_expenses", "Administrative expenses", "ADMIN_EXPENSES", 40),
        ("operating_expenses", "Rent", "ADMIN_EXPENSES", 35),
        ("operating_expenses", "Advertising", "DISTRIBUTION_COSTS", 35),
        ("operating_expenses", "Operating Expenses", None, None),
        ("operating_expenses", "Overheads", None, None),
        ("operating_expenses", "Wages", None, None),
        ("operating_expenses", "Carriage inwards", None, None),
        ("operating_expenses", "Hire purchase", None, None),
        ("loans", "Bank overdraft", "BANK_OVERDRAFT", 40),
        ("loans", "Director's loan", "DIRECTOR_LOAN", 40),
        ("loans", "Loan - due within one year", "LOANS_LT1Y", 40),
        ("loans", "Loan - due after more than one year", "LOANS_GT1Y", 40),
        ("loans", "Hire purchase within one year", "LEASE_LIABILITY_LT1Y", 40),
        ("loans", "Bank loan", None, None),
        ("loans", "Hire purchase", None, None),
        ("tax", "VAT payable", "VAT_CONTROL", 40),
        ("tax", "PAYE/PRSI", "PAYE_PRSI", 40),
        ("tax", "Corporation tax payable", "CORP_TAX", 40),
        ("tax", "Tax charge", "TAX_CHARGE", 40),
        ("tax", "Corporation tax", None, None),
        ("tax", "Deferred tax", "DEFERRED_TAX", 35),
        ("depreciation", "Depreciation charge", "DEPRECIATION_CHARGE", 40),
        ("depreciation", "Depreciation", None, None),
        ("depreciation", "Depreciation - motor vehicles", None, None),
        ("amortisation", "Amortisation charge", "AMORTISATION_CHARGE", 40),
        ("amortisation", "Accumulated amortisation", "FA_INTANGIBLE_AMORT", 40),
        ("amortisation", "Amortisation", None, None),
        ("intangible_assets", "Goodwill", "FA_INTANGIBLE_COST", 40),
        ("intangible_assets", "Software subscription", None, None),
        ("intangible_assets", "Licence fee", None, None),
        ("intangible_assets", "Intangible assets", None, None),
        ("intangible_assets", "Business development", None, None),
    )
    for product1, name, line, score in cases:
        assert _hit(product1, name) == (line, score), name
        if line is not None:
            assert line in allowed_sublines(product1)


def test_two_homes_in_one_name_are_not_suggested() -> None:
    assert _hit("operating_expenses", "Rent and carriage outwards") == (None, None)
    assert _hit("property_plant_equipment", "Land and plant") == (None, None)


def test_amortisation_charge_reduces_profit_inside_admin_expenses() -> None:
    mapped = {
        "REVENUE": Decimal("-100"),
        "ADMIN_EXPENSES": Decimal("10"),
        "DEPRECIATION_CHARGE": Decimal("4"),
        "AMORTISATION_CHARGE": Decimal("3"),
        "RETAINED_EARNINGS": Decimal("83"),
    }
    income = build_income_statement(mapped, {})
    rows = {label: current for label, current, _prior in income["rows"]}
    assert rows["Administrative expenses (including depreciation)"] == Decimal("-17")
    assert income["profit"] == Decimal("83")
    prior = prior_from_mapped(mapped)
    assert prior["ADMIN_EXPENSES"] == Decimal("10")
    assert prior["DEPRECIATION"] == Decimal("4")
    assert prior["AMORTISATION"] == Decimal("3")
