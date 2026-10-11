"""Dashboard notices for letterhead facts that look wrong.

The Irish pack stores the thresholds in ``data_checks``. Each threshold is a
legal judgement marked reviewer-to-confirm. This module does not draft
statutory wording. A missing pack key falls back to the same numbers shipped
in that pack, so a dashboard still raises the check.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.models.company import Company
from app.schemas.company_details import DirectorRecord
from app.services.reconciliation import ReconciliationCheck
from findraft.engine.pack import pack_dir
from findraft.models.year_end import YearEnd

_IRISH_PACK = "frs102-1a-ie"
_TOLERANCE = Decimal("0.01")
_COUNTIES = (
    "carlow",
    "cavan",
    "clare",
    "cork",
    "donegal",
    "dublin",
    "galway",
    "kerry",
    "kildare",
    "kilkenny",
    "laois",
    "leitrim",
    "limerick",
    "longford",
    "louth",
    "mayo",
    "meath",
    "monaghan",
    "offaly",
    "roscommon",
    "sligo",
    "tipperary",
    "waterford",
    "westmeath",
    "wexford",
    "wicklow",
)
# Routing key plus four characters. Dublin 6W is a routing key of its own.
_EIRCODE = re.compile(
    r"(?<![A-Za-z0-9])(?:[AC-FHKNPRTV-Y]\d{2}|D6W)[ -]?[0-9AC-FHKNPRTV-Y]{4}(?![A-Za-z0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DataCheckRules:
    suffixes: tuple[str, ...]
    first_period_max_months: int
    company_number_min_digits: int
    company_number_max_digits: int
    employee_notice_above: int
    turnover_per_employee_floor: Decimal


_DEFAULT_RULES = DataCheckRules(
    suffixes=("Limited", "Ltd", "Teoranta", "Teo"),
    first_period_max_months=18,
    company_number_min_digits=5,
    company_number_max_digits=7,
    employee_notice_above=50,
    turnover_per_employee_floor=Decimal("2000.00"),
)


def company_data_checks(
    company: Company,
    year_end: YearEnd,
    *,
    turnover: Decimal | None = None,
    profit_before_tax: Decimal | None = None,
    tax_charge: Decimal | None = None,
    corporation_tax: Decimal | None = None,
    subsequent_events_answered: bool | None = None,
) -> tuple[ReconciliationCheck, ...]:
    """Irish-pack data checks. Notices are omitted when they pass."""
    if year_end.pack_id != _IRISH_PACK:
        return ()
    rules = _rules(year_end)
    checks: list[ReconciliationCheck] = [_name_suffix(company.name, rules)]
    period = _first_period(company, year_end, rules)
    if period is not None:
        checks.append(period)
    office = _office_notice(company.registered_office)
    if office is not None:
        checks.append(office)
    number = _number_notice(company.company_number, rules)
    if number is not None:
        checks.append(number)
    appointment = _appointment_notice(company)
    if appointment is not None:
        checks.append(appointment)
    spelling = _spelling_notice(company)
    if spelling is not None:
        checks.append(spelling)
    employees = _employee_notices(company.average_employees, turnover, rules)
    checks.extend(employees)
    tax = _tax_notice(profit_before_tax, tax_charge, corporation_tax)
    if tax is not None:
        checks.append(tax)
    events = _events_notice(subsequent_events_answered)
    if events is not None:
        checks.append(events)
    return tuple(checks)


def _rules(year_end: YearEnd) -> DataCheckRules:
    try:
        raw = json.loads(
            (pack_dir(year_end.pack_id, year_end.pack_version) / "pack.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, ValueError):
        return _DEFAULT_RULES
    payload = raw.get("data_checks") if isinstance(raw, dict) else None
    if not isinstance(payload, dict):
        return _DEFAULT_RULES
    suffixes = payload.get("legal_form_suffixes")
    stored = (
        tuple(
            item.strip() for item in suffixes if isinstance(item, str) and item.strip()
        )
        if isinstance(suffixes, list)
        else ()
    )
    floor = _decimal(payload.get("turnover_per_employee_floor"))
    return DataCheckRules(
        suffixes=stored or _DEFAULT_RULES.suffixes,
        first_period_max_months=_positive_int(
            payload.get("first_period_max_months"),
            _DEFAULT_RULES.first_period_max_months,
        ),
        company_number_min_digits=_positive_int(
            payload.get("company_number_min_digits"),
            _DEFAULT_RULES.company_number_min_digits,
        ),
        company_number_max_digits=_positive_int(
            payload.get("company_number_max_digits"),
            _DEFAULT_RULES.company_number_max_digits,
        ),
        employee_notice_above=_positive_int(
            payload.get("employee_notice_above"),
            _DEFAULT_RULES.employee_notice_above,
        ),
        turnover_per_employee_floor=(
            floor if floor is not None else _DEFAULT_RULES.turnover_per_employee_floor
        ),
    )


def _name_suffix(name: str, rules: DataCheckRules) -> ReconciliationCheck:
    pattern = "|".join(re.escape(item) for item in rules.suffixes)
    matched = re.search(rf"(?:^|\s)(?:{pattern})\.?\s*$", name.strip(), re.IGNORECASE)
    if matched is not None:
        return _check(
            "V-CO-010",
            "WARNING",
            True,
            "The company name ends with a legal-form suffix.",
        )
    return _check(
        "V-CO-010",
        "WARNING",
        False,
        "The company name does not end with " f"{_or_list(list(rules.suffixes))}.",
    )


def _first_period(
    company: Company, year_end: YearEnd, rules: DataCheckRules
) -> ReconciliationCheck | None:
    if not year_end.first_financial_period:
        return None
    reasons: list[str] = []
    incorporated = company.incorporated_on
    start = year_end.period_start
    end = year_end.period_end
    if incorporated is None:
        reasons.append(
            "The date of incorporation has not been recorded. "
            "A first financial period has to start on that date."
        )
    elif start != incorporated:
        shown = "not recorded" if start is None else _spoken(start)
        reasons.append(
            f"This first financial period starts on {shown}, but the company "
            f"was incorporated on {_spoken(incorporated)}. The first period "
            "has to start on the incorporation date."
        )
    months = rules.first_period_max_months
    if start is not None and end >= _add_months(start, months):
        reasons.append(f"This first financial period is longer than {months} months.")
    if not reasons:
        return _check(
            "V-CO-011",
            "WARNING",
            True,
            "The first financial period starts on the date of incorporation "
            f"and is not longer than {months} months.",
        )
    return _check("V-CO-011", "WARNING", False, " ".join(reasons))


def _office_notice(office: str | None) -> ReconciliationCheck | None:
    text = "" if office is None else office.strip()
    if text == "" or _office_looks_irish(text):
        return None
    return _check(
        "V-CO-012",
        "NOTICE",
        False,
        "The registered office does not look like an Irish address. "
        "No Eircode and no Irish county were found.",
    )


def _office_looks_irish(office: str) -> bool:
    if _EIRCODE.search(office) is not None:
        return True
    folded = office.casefold()
    for county in _COUNTIES:
        if re.search(rf"(?<![a-z]){county}(?![a-z])", folded) is not None:
            return True
    return False


def _number_notice(
    number: str | None, rules: DataCheckRules
) -> ReconciliationCheck | None:
    text = "" if number is None else re.sub(r"\s+", "", number.strip())
    if text == "":
        return None
    low = rules.company_number_min_digits
    high = rules.company_number_max_digits
    if text.isdigit() and low <= len(text) <= high:
        return None
    return _check(
        "V-CO-013",
        "NOTICE",
        False,
        f"Company number '{text}' is not {low} to {high} digits.",
    )


def _directors(company: Company) -> list[DirectorRecord]:
    # Imported here so company_details can call this module while it loads.
    from app.services.company_details import _read_directors

    return _read_directors(company.directors)


def _appointment_notice(company: Company) -> ReconciliationCheck | None:
    incorporated = company.incorporated_on
    if incorporated is None:
        return None
    dated = [row for row in _directors(company) if row.appointed_on is not None]
    if not dated:
        return None
    earlier = any(
        row.appointed_on is not None and row.appointed_on <= incorporated
        for row in dated
    )
    if earlier:
        return None
    late = [
        row
        for row in dated
        if row.appointed_on is not None and row.appointed_on > incorporated
    ]
    if not late:
        return None
    listed = ", ".join(
        f"{row.name} ({_spoken(row.appointed_on)})"
        for row in late
        if row.appointed_on is not None
    )
    return _check(
        "V-CO-014",
        "NOTICE",
        False,
        f"Director appointment is after incorporation on {_spoken(incorporated)} "
        f"and no earlier director is recorded: {listed}.",
    )


def _spelling_notice(company: Company) -> ReconciliationCheck | None:
    directors = _directors(company)
    secretary = "" if company.secretary is None else company.secretary.strip()
    lower: list[str] = []
    for row in directors:
        if _all_lowercase(row.name):
            lower.append(f"Director '{row.name}'")
    if secretary and _all_lowercase(secretary):
        lower.append(f"Company secretary '{secretary}'")
    pairs: list[str] = []
    if secretary:
        for row in directors:
            if _one_edit(row.name, secretary):
                pairs.append(
                    f"Director '{row.name}' differs by one letter from the "
                    f"company secretary '{secretary}'."
                )
    if not lower and not pairs:
        return None
    parts: list[str] = []
    if lower:
        verb = "is" if len(lower) == 1 else "are"
        parts.append(f"{_and_list(lower)} {verb} all in lowercase.")
    parts.extend(pairs)
    parts.append("Check the spelling.")
    return _check("V-CO-015", "NOTICE", False, " ".join(parts))


def _employee_notices(
    employees: int | None, turnover: Decimal | None, rules: DataCheckRules
) -> tuple[ReconciliationCheck, ...]:
    if employees is None:
        return ()
    found: list[ReconciliationCheck] = []
    if employees > rules.employee_notice_above:
        found.append(
            _check(
                "V-CO-016",
                "NOTICE",
                False,
                f"Average employees are {employees:,}, which is above "
                f"{rules.employee_notice_above:,}. Check this figure.",
            )
        )
    floor = rules.turnover_per_employee_floor
    if (
        employees > 0
        and turnover is not None
        and turnover > _TOLERANCE
        and (turnover / Decimal(employees)) < floor
    ):
        found.append(
            _check(
                "V-CO-017",
                "NOTICE",
                False,
                "Turnover per employee is below "
                f"{_plain_amount(floor)}. Check the employee count against turnover.",
            )
        )
    return tuple(found)


def _tax_notice(
    profit_before_tax: Decimal | None,
    tax_charge: Decimal | None,
    corporation_tax: Decimal | None,
) -> ReconciliationCheck | None:
    if profit_before_tax is None or tax_charge is None or corporation_tax is None:
        return None
    if profit_before_tax <= _TOLERANCE:
        return None
    if abs(tax_charge) > _TOLERANCE:
        return None
    # A credit balance is a creditor. Debit-positive storage makes that negative.
    if corporation_tax < -_TOLERANCE:
        return None
    return _check(
        "V-CO-018",
        "NOTICE",
        False,
        "There is a profit before tax and no tax charge or corporation tax "
        "creditor. Check whether tax should be recorded.",
    )


def _events_notice(answered: bool | None) -> ReconciliationCheck | None:
    if answered is None or answered:
        return None
    return _check(
        "V-CO-019",
        "NOTICE",
        False,
        "The question about events after the balance sheet date has not been answered.",
    )


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    if month == 12:
        following = date(year + 1, 1, 1)
    else:
        following = date(year, month + 1, 1)
    last_day = (following - timedelta(days=1)).day
    return date(year, month, min(start.day, last_day))


def _one_edit(left: str, right: str) -> bool:
    shorter = left.casefold()
    longer = right.casefold()
    if shorter == longer:
        return False
    if abs(len(shorter) - len(longer)) > 1:
        return False
    if len(shorter) > len(longer):
        shorter, longer = longer, shorter
    edits = 0
    index = 0
    offset = 0
    while index < len(shorter) and offset < len(longer):
        if shorter[index] == longer[offset]:
            index += 1
            offset += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(shorter) == len(longer):
            index += 1
        offset += 1
    edits += (len(longer) - offset) + (len(shorter) - index)
    return edits == 1


def _all_lowercase(name: str) -> bool:
    letters = [character for character in name if character.isalpha()]
    return bool(letters) and all(character.islower() for character in letters)


def _spoken(value: date) -> str:
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _or_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if not items:
        return ""
    return f"{', '.join(items[:-1])}, or {items[-1]}"


def _and_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _plain_amount(amount: Decimal) -> str:
    quantized = amount.quantize(Decimal("0.01"))
    if quantized == quantized.to_integral_value():
        return f"{int(quantized):,}"
    return f"{quantized:,.2f}"


def _positive_int(value: object, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return fallback
    if value <= 0:
        return fallback
    return value


def _decimal(value: object) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def _check(code: str, severity: str, passed: bool, message: str) -> ReconciliationCheck:
    return ReconciliationCheck(
        code=code, severity=severity, passed=passed, message=message
    )
