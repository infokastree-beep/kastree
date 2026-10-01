"""Week 5: FinDraft exclusions in Product 1, and the engine line-name contract.

Product 1 canonical lines (revenue, cash, intangible_assets, …) stay on
``map_accounts``. Statutory names (BANK_OVERDRAFT, FA_INTANGIBLE_AMORT, …)
come from ``suggest_statutory_mapping`` in the same module. No new table, so
there is no isolation test in this module.
"""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from unittest.mock import MagicMock

from findraft.engine.mapping import aggregate, classification, suggest_mapping
from findraft.engine.pack import pack_dir
from findraft.engine.schemas import TBLine
from findraft.engine.statements import build_sofp

from app.services.mapper import (
    PriorConfirmedMapping,
    findraft_excluded_lines,
    map_accounts,
    map_accounts_with_llm,
    suggest_statutory_mapping,
)


class _Account:
    def __init__(self, account_code: str, account_name: str) -> None:
        self.account_code = account_code
        self.account_name = account_name


class _Nominal:
    def __init__(self, nominal_code: str, account_name: str) -> None:
        self.nominal_code = nominal_code
        self.account_name = account_name


def _pack() -> object:
    path = pack_dir() / "mapping-defaults.py"
    spec = importlib.util.spec_from_file_location("week5_mapping_defaults", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine(code: str, name: str, module: object) -> tuple[object, object]:
    suggestion = suggest_mapping(
        _Nominal(code, name),
        {},
        module.KEYWORD_SCORES,  # type: ignore[attr-defined]
        module.CODE_RANGES,  # type: ignore[attr-defined]
    )
    return suggestion[0], suggestion[1]


def _completion(canonical_line: str) -> MagicMock:
    message = MagicMock()
    message.content = (
        '{"mappings":[{"index":1,"canonical_line":"%s",'
        '"reasoning":"model","confidence":0.91}]}' % canonical_line
    )
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def test_pack_keywords_match_the_engine_except_overdraft() -> None:
    """Every pack keyword emits the engine line. Overdraft is the exception."""
    module = _pack()
    for keyword, (expected_line, _) in module.KEYWORD_SCORES.items():  # type: ignore[attr-defined]
        if keyword == "overdraft":
            continue
        engine_line, engine_score = _engine("9999", keyword, module)
        got = suggest_statutory_mapping("9999", keyword)
        assert got.canonical_line == engine_line == expected_line
        assert got.confidence == engine_score
        assert got.confidence < 80


def test_overdraft_emits_bank_overdraft_not_cash_or_loans() -> None:
    module = _pack()
    engine_line, engine_score = _engine("2300", "Bank overdraft", module)
    assert engine_line == "LOANS_LT1Y"
    got = suggest_statutory_mapping("2300", "Bank overdraft")
    assert got.canonical_line == "BANK_OVERDRAFT"
    assert got.canonical_line != "CASH"
    assert got.canonical_line != "LOANS_LT1Y"
    assert got.confidence == engine_score
    assert got.confidence < 80
    assert "CASH" in findraft_excluded_lines("Bank overdraft")


def test_accumulated_amortisation_emits_fa_intangible_amort() -> None:
    module = _pack()
    for name in (
        "Accumulated amortisation - software",
        "Accumulated Amortisation",
        "Provision for Amortisation",
    ):
        engine_line, _engine_score = _engine("1550", name, module)
        assert engine_line is None
        got = suggest_statutory_mapping("1550", name)
        assert got.canonical_line == "FA_INTANGIBLE_AMORT"
        assert got.confidence == 40
        assert got.confidence < 80


def test_intangible_cost_names_emit_fa_intangible_cost() -> None:
    for name in ("Goodwill", "Patents", "Trademarks", "Intangible assets"):
        got = suggest_statutory_mapping("1540", name)
        assert got.canonical_line == "FA_INTANGIBLE_COST"
        assert got.confidence < 80


def test_amortisation_charge_is_not_the_contra_line() -> None:
    got = suggest_statutory_mapping("7100", "Amortisation - Software")
    assert got.canonical_line != "FA_INTANGIBLE_AMORT"
    assert got.canonical_line != "FA_INTANGIBLE_COST"
    product1 = map_accounts([_Account("7100", "Amortisation - Software")], [])[0]
    assert product1.canonical_line == "amortisation"


def test_pl_wording_does_not_emit_a_balance_sheet_line() -> None:
    assert suggest_statutory_mapping("7100", "Overdraft interest").canonical_line == (
        "INTEREST_PAYABLE"
    )
    assert (
        suggest_statutory_mapping("7600", "Bank overdraft charges").canonical_line
        != "BANK_OVERDRAFT"
    )
    written_off = suggest_statutory_mapping("7000", "Development costs written off")
    assert written_off.canonical_line != "FA_INTANGIBLE_COST"
    assert written_off.canonical_line not in findraft_excluded_lines(
        "Development costs written off"
    )


def test_golden_chart_matches_the_engine() -> None:
    module = _pack()
    cases = (
        ("5000", "Cost of sales", "COST_OF_SALES"),
        ("1201", "Bank current account", "CASH"),
        ("6100", "Interest receivable", "INTEREST_RECEIVABLE"),
        ("1505", "Accumulated depreciation", "FA_ACCUM_DEP"),
        ("7100", "Interest payable", "INTEREST_PAYABLE"),
        ("1600", "Fixtures and fittings", "FA_FIXTURES_COST"),
        ("1500", "Land and buildings", "FA_LAND_BUILDINGS"),
        ("1350", "Investments", "FA_INVESTMENTS"),
        ("2220", "VAT control", "VAT_CONTROL"),
        ("2230", "PAYE/PRSI", "PAYE_PRSI"),
        ("2400", "Director's loan", "DIRECTOR_LOAN"),
        ("3105", "Share premium", "SHARE_PREMIUM"),
        ("3300", "Provisions", "PROVISIONS"),
        ("2320", "Deferred tax", "DEFERRED_TAX"),
        ("2250", "Accrued income", "ACCRUED_INCOME"),
        ("2260", "Deferred income", "DEFERRED_INCOME"),
        ("1201", "Bank - Current a/c", "CASH"),
        ("1202", "Bank Acc", "CASH"),
        ("1203", "Curr a/c", "CASH"),
        ("1200", "Bank Current Account", "CASH"),
        ("1204", "Cash at bank", "CASH"),
        ("2300", "Bank Loan - Long Term", "LOANS_GT1Y"),
        ("2700", "Interest on Bank Loan", "INTEREST_PAYABLE"),
        ("2300", "Bank borrowings", "LOANS_GT1Y"),
        ("2301", "Bank Mortgage", "LOANS_LT1Y"),
    )
    for code, name, expected in cases:
        engine_line, engine_score = _engine(code, name, module)
        got = suggest_statutory_mapping(code, name)
        assert engine_line == expected
        assert got.canonical_line == expected
        assert got.confidence == engine_score
        assert got.canonical_line != "CASH" or "CASH" not in findraft_excluded_lines(
            name
        )
        assert got.confidence < 80


def test_loan_and_tax_names_never_suggest_cash() -> None:
    names = (
        "Bank Loan - Long Term",
        "Director's loan",
        "Bank borrowings",
        "Bank Mortgage",
        "Hire purchase",
        "Finance lease",
        "Credit card",
        "VAT control",
        "PAYE/PRSI",
        "Corporation tax",
        "Income tax",
    )
    for name in names:
        assert "CASH" in findraft_excluded_lines(name)
        got = suggest_statutory_mapping("2300", name)
        assert got.canonical_line != "CASH"


def test_heuristic_cap_blocks_auto_confirm() -> None:
    got = suggest_statutory_mapping(
        "4000",
        "Sales",
        keyword_scores={"sales": ("REVENUE", 100)},
        code_ranges={(4000, 4099): "REVENUE"},
    )
    assert got.canonical_line == "REVENUE"
    assert got.confidence == 79
    assert classification(got.confidence) != "AUTO_CONFIRM"


def test_prior_exact_engine_line_is_the_only_auto_confirm() -> None:
    prior = [
        PriorConfirmedMapping(
            source_code="1100",
            source_name="Trade debtors",
            canonical_line="TRADE_DEBTORS",
        )
    ]
    exact = suggest_statutory_mapping("1100", "Trade debtors", prior)
    assert exact.canonical_line == "TRADE_DEBTORS"
    assert exact.confidence == 100
    assert exact.signals == ("prior_exact",)
    assert classification(exact.confidence) == "AUTO_CONFIRM"

    code_only = suggest_statutory_mapping("1100", "Debtors control", prior)
    assert code_only.canonical_line == "TRADE_DEBTORS"
    assert code_only.confidence == 60
    assert code_only.signals == ("prior_code",)
    assert classification(code_only.confidence) != "AUTO_CONFIRM"

    product1_prior = [
        PriorConfirmedMapping(
            source_code="4000",
            source_name="Sales",
            canonical_line="revenue",
        )
    ]
    statutory = suggest_statutory_mapping("4000", "Sales", product1_prior)
    assert statutory.canonical_line == "REVENUE"
    assert statutory.confidence < 80
    assert "prior_exact" not in statutory.signals


def test_statement_builder_accepts_the_new_lines() -> None:
    """Product 2 statements consume these names. aggregate re-homes overdrawn cash."""
    accounts = (
        TBLine("1205", "Bank overdraft", Decimal("0"), Decimal("5000.00")),
        TBLine("1550", "Accumulated amortisation", Decimal("0"), Decimal("1000.00")),
        TBLine("1540", "Goodwill", Decimal("8000.00"), Decimal("0")),
        TBLine("3000", "Share capital", Decimal("0"), Decimal("2000.00")),
    )
    mappings: dict[str, str] = {}
    for account in accounts:
        suggestion = suggest_statutory_mapping(
            account.nominal_code, account.account_name
        )
        assert suggestion.canonical_line is not None
        mappings[account.nominal_code] = suggestion.canonical_line

    aggregated = aggregate(accounts, mappings)
    assert aggregated["BANK_OVERDRAFT"] == Decimal("-5000.00")
    assert aggregated["FA_INTANGIBLE_AMORT"] == Decimal("-1000.00")
    assert aggregated["FA_INTANGIBLE_COST"] == Decimal("8000.00")
    built = build_sofp(aggregated, {})
    rows = {label: current for label, current, _prior in built["rows"]}
    assert rows["Intangible assets"] == Decimal("7000.00")
    assert rows["Creditors: amounts falling due within one year"] == Decimal("-5000.00")

    overdrawn = TBLine("1200", "Bank current account", Decimal("0"), Decimal("250.00"))
    cash = suggest_statutory_mapping(overdrawn.nominal_code, overdrawn.account_name)
    assert cash.canonical_line == "CASH"
    rehomed = aggregate([overdrawn], {"1200": cash.canonical_line})
    assert rehomed["BANK_OVERDRAFT"] == Decimal("-250.00")
    assert "CASH" not in rehomed


def test_product1_canonical_lines_stay_on_the_existing_chart() -> None:
    accounts = [
        _Account("1550", "Accumulated amortisation - software"),
        _Account("1450", "Accumulated Depreciation"),
        _Account("1200", "Bank current account"),
        _Account("1205", "Bank overdraft"),
        _Account("7100", "Amortisation - Software"),
        _Account("7000", "Depreciation - Buildings"),
        _Account("1800", "VAT Recoverable"),
    ]
    results = map_accounts(accounts, [])
    assert [row.canonical_line for row in results] == [
        "intangible_assets",
        "property_plant_equipment",
        None,
        None,
        "amortisation",
        "depreciation",
        "other_receivables",
    ]


def test_pl_wording_strips_a_balance_sheet_product1_suggestion() -> None:
    result = map_accounts(
        [_Account("1450", "Accumulated depreciation charges")],
        [],
    )[0]
    assert result.canonical_line is None
    assert result.method is None


def test_fuzzy_cash_is_refused_for_a_loan_name_and_kept_for_a_bank_account() -> None:
    loan = map_accounts(
        [_Account("2300", "Bank Loan")],
        [PriorConfirmedMapping("9999", "Bank Loan", "cash")],
    )[0]
    assert loan.canonical_line is None
    assert loan.method is None

    bank = map_accounts(
        [_Account("1200", "Bank Current Account")],
        [PriorConfirmedMapping("9999", "Bank Current Account", "cash")],
    )[0]
    assert bank.canonical_line == "cash"
    assert bank.method == "fuzzy"
    assert bank.confidence == Decimal("1.00")


def test_confirmed_exact_cash_on_a_loan_name_is_not_overridden() -> None:
    """A human-confirmed prior exact match stays. Exclusions apply to heuristics."""
    result = map_accounts(
        [_Account("2300", "Bank Loan")],
        [PriorConfirmedMapping("2300", "Bank Loan", "cash")],
    )[0]
    assert result.canonical_line == "cash"
    assert result.method == "exact"
    assert result.confidence == Decimal("1.00")


def test_llm_cash_is_refused_for_loan_and_tax_names() -> None:
    for name in ("Bank Loan - Long Term", "VAT control", "Director's loan"):
        result = map_accounts_with_llm(
            [_Account("2300", name)],
            [],
            openai_client=_completion("cash"),
            sleep=lambda _seconds: None,
        )[0]
        assert result.canonical_line is None
        assert result.method == "llm"

    kept = map_accounts_with_llm(
        [_Account("1200", "Cash at bank")],
        [],
        openai_client=_completion("cash"),
        sleep=lambda _seconds: None,
    )[0]
    assert kept.canonical_line == "cash"
    assert kept.confidence == Decimal("0.91")
    assert kept.method == "llm"
