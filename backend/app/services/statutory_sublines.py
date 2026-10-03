"""Suggest a statutory sub-line for the seven Product 1 lines that have no
single home. A suggestion is not posted. The accountant confirms it.

Matching is the word-boundary rule in ``findraft.engine.mapping``: both
sides of the phrase, longest phrase first, exclusions before a hit. Scores
are 35 or 40, under the pre-select cap of 80. 100 is only a stored
confirmation, and that score is applied by the caller.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_AMORT = re.compile(
    r"\b(?:un)?amort(?:isation|ization|ised|ized)\b",
    re.IGNORECASE,
)

_PPE = (
    "FA_LAND_BUILDINGS",
    "FA_PLANT_COST",
    "FA_FIXTURES_COST",
    "FA_MOTOR_COST",
    "FA_ACCUM_DEP",
    "ROU_ASSETS",
)
_OPEX = ("DISTRIBUTION_COSTS", "ADMIN_EXPENSES")
_LOANS = (
    "LOANS_LT1Y",
    "LOANS_GT1Y",
    "BANK_OVERDRAFT",
    "DIRECTOR_LOAN",
    "LEASE_LIABILITY_LT1Y",
    "LEASE_LIABILITY_GT1Y",
)
_TAX = ("TAX_CHARGE", "CORP_TAX", "DEFERRED_TAX", "VAT_CONTROL", "PAYE_PRSI")
_DEPRECIATION = ("DEPRECIATION_CHARGE", "FA_ACCUM_DEP")
_AMORTISATION = ("AMORTISATION_CHARGE", "FA_INTANGIBLE_AMORT")
_INTANGIBLE = ("FA_INTANGIBLE_COST", "FA_INTANGIBLE_AMORT")

_CHOICES: dict[str, tuple[str, ...]] = {
    "property_plant_equipment": _PPE,
    "operating_expenses": _OPEX,
    "loans": _LOANS,
    "tax": _TAX,
    "depreciation": _DEPRECIATION,
    "amortisation": _AMORTISATION,
    "intangible_assets": _INTANGIBLE,
}


@dataclass(frozen=True)
class SublineHit:
    """A name-pattern suggestion. ``score`` is 35 or 40, never 100."""

    engine_line: str
    score: int


def normalize_account_name(value: str) -> str:
    """Case-fold and collapse whitespace. Matching uses this form."""
    return re.sub(r"\s+", " ", value.strip().casefold())


def needs_statutory_subline(product1_line: str) -> bool:
    """True for the seven Product 1 lines that have no single engine home."""
    return product1_line.strip().casefold() in _CHOICES


def allowed_sublines(product1_line: str) -> tuple[str, ...]:
    """Engine lines the dropdown may offer for this Product 1 line."""
    return _CHOICES.get(product1_line.strip().casefold(), ())


def suggest_subline(product1_line: str, account_name: str) -> SublineHit | None:
    """One suggested engine line, or None when the name is ambiguous."""
    line = product1_line.strip().casefold()
    name = normalize_account_name(account_name)
    if not line or not name or line not in _CHOICES:
        return None
    if line == "property_plant_equipment":
        return _property_plant_equipment(name)
    if line == "operating_expenses":
        return _operating_expenses(name)
    if line == "loans":
        return _loans(name)
    if line == "tax":
        return _tax(name)
    if line == "depreciation":
        return _depreciation(name)
    if line == "amortisation":
        return _amortisation(name)
    return _intangible_assets(name)


def _has(name: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", name) is not None


def _any(name: str, phrases: tuple[str, ...]) -> bool:
    return any(_has(name, phrase) for phrase in phrases)


_Exclude = Callable[[str], bool]


def _best(
    name: str,
    rules: tuple[tuple[tuple[str, ...], str, int, _Exclude | None], ...],
) -> SublineHit | None:
    hits: list[tuple[str, int]] = []
    for phrases, engine_line, score, exclude in rules:
        if exclude is not None and exclude(name):
            continue
        if _any(name, phrases):
            hits.append((engine_line, score))
    if not hits:
        return None
    if len({engine_line for engine_line, _score in hits}) != 1:
        return None
    engine_line, score = max(hits, key=lambda item: item[1])
    return SublineHit(engine_line, score)


def _amort_name(name: str) -> bool:
    return _AMORT.search(name) is not None


def _motor_running(name: str) -> bool:
    return _any(name, ("expense", "expenses", "running", "repairs", "fuel", "insurance"))


def _not_land(name: str) -> bool:
    return _any(name, ("leasehold", "investment property", "right-of-use", "right of use", "landlord"))


def _bare_equipment(name: str) -> bool:
    return _any(name, ("office equipment", "computer equipment")) or name == "equipment"


def _property_plant_equipment(name: str) -> SublineHit | None:
    if _amort_name(name):
        return None
    if _any(name, ("right-of-use", "right of use")) and _accumulated_depreciation(name):
        return None
    if _accumulated_depreciation(name):
        return SublineHit("FA_ACCUM_DEP", 40)
    if _has(name, "right-of-use asset") or _has(name, "right of use asset"):
        return SublineHit("ROU_ASSETS", 40)
    return _best(
        name,
        (
            (
                ("land and buildings", "freehold land", "freehold property", "freehold buildings"),
                "FA_LAND_BUILDINGS",
                40,
                _not_land,
            ),
            (
                ("land", "buildings", "premises"),
                "FA_LAND_BUILDINGS",
                35,
                _not_land,
            ),
            (("plant and machinery",), "FA_PLANT_COST", 40, None),
            (("plant", "machinery"), "FA_PLANT_COST", 35, _bare_equipment),
            (
                ("fixtures and fittings", "fixtures, fittings"),
                "FA_FIXTURES_COST",
                40,
                None,
            ),
            (("fixtures", "fittings", "furniture"), "FA_FIXTURES_COST", 35, None),
            (
                ("motor vehicles", "motor vans"),
                "FA_MOTOR_COST",
                40,
                _motor_running,
            ),
            (("vans", "lorries", "trucks"), "FA_MOTOR_COST", 35, _motor_running),
        ),
    )


def _accumulated_depreciation(name: str) -> bool:
    if _any(
        name,
        (
            "accumulated depreciation",
            "provision for depreciation",
            "depreciation brought forward",
            "depreciation b/fwd",
        ),
    ):
        return True
    return _has(name, "a/dep") and (_has(name, "depreciation") or _has(name, "depn"))


def _inwards(name: str) -> bool:
    return _any(name, ("inwards", "inward"))


def _not_admin_cost(name: str) -> bool:
    return _any(name, ("income", "receivable", "received", "administrator"))


def _advertising_wage(name: str) -> bool:
    return _any(name, ("wages", "salaries"))


def _fixed_asset_selling(name: str) -> bool:
    return _has(name, "fixed asset")


def _operating_expenses(name: str) -> SublineHit | None:
    if _has(name, "hire purchase") or _has(name, "finance lease"):
        return None
    return _best(
        name,
        (
            (
                (
                    "distribution costs",
                    "carriage outwards",
                    "sales commission",
                    "sales wages",
                ),
                "DISTRIBUTION_COSTS",
                40,
                _inwards,
            ),
            (
                ("distribution", "selling", "delivery"),
                "DISTRIBUTION_COSTS",
                35,
                lambda text: _inwards(text) or _fixed_asset_selling(text),
            ),
            (
                ("administrative expenses", "administration expenses"),
                "ADMIN_EXPENSES",
                40,
                None,
            ),
            (
                (
                    "rent and rates",
                    "light and heat",
                    "professional fees",
                    "accountancy fees",
                    "audit fees",
                    "bank charges",
                ),
                "ADMIN_EXPENSES",
                40,
                _not_admin_cost,
            ),
            (
                (
                    "rent",
                    "rates",
                    "insurance",
                    "telephone",
                    "stationery",
                    "accountancy",
                    "audit",
                    "legal",
                    "subscriptions",
                    "admin",
                    "administrative",
                    "administration",
                ),
                "ADMIN_EXPENSES",
                35,
                _not_admin_cost,
            ),
            (
                ("advertising", "marketing"),
                "DISTRIBUTION_COSTS",
                35,
                _advertising_wage,
            ),
        ),
    )


_DIRECTOR = (
    "director's loan",
    "directors' loan",
    "director loan",
    "directors loan",
    "director current account",
    "directors current account",
)
_SHORT = (
    "within one year",
    "less than one year",
    "less than 1 year",
    "short-term",
    "short term",
)
_LONG = (
    "after more than one year",
    "more than one year",
    "more than 1 year",
    "non-current",
    "non current",
    "long-term",
    "long term",
    "after five years",
    "after 5 years",
)
_LEASE = ("finance lease", "hire purchase", "lease liability", "lease liabilities")
_LEASE_ASSET = ("leasehold", "right-of-use", "right of use", "rou asset")


def _loans(name: str) -> SublineHit | None:
    if _has(name, "overdraft"):
        return SublineHit("BANK_OVERDRAFT", 40)
    if _any(name, _DIRECTOR):
        return SublineHit("DIRECTOR_LOAN", 40)
    lease = _any(name, _LEASE)
    asset = _any(name, _LEASE_ASSET)
    short = _any(name, _SHORT)
    long = _any(name, _LONG)
    if lease and asset:
        return None
    if lease and short and long:
        return None
    if lease and short:
        return SublineHit("LEASE_LIABILITY_LT1Y", 40)
    if lease and long:
        return SublineHit("LEASE_LIABILITY_GT1Y", 40)
    if lease:
        return None
    if short and long:
        return None
    if short:
        return SublineHit("LOANS_LT1Y", 40)
    if long:
        return SublineHit("LOANS_GT1Y", 40)
    return None


def _tax(name: str) -> SublineHit | None:
    if _has(name, "vat") or _has(name, "value added tax"):
        return SublineHit("VAT_CONTROL", 40)
    if _any(name, ("paye", "prsi", "usc")):
        return SublineHit("PAYE_PRSI", 40)
    if _has(name, "deferred tax charge") or _has(name, "deferred tax expense"):
        return SublineHit("TAX_CHARGE", 40)
    if _has(name, "deferred tax"):
        return SublineHit("DEFERRED_TAX", 35)
    charge = _any(
        name,
        (
            "corporation tax charge",
            "corporation tax expense",
            "corp tax charge",
            "tax charge",
            "tax expense",
        ),
    )
    creditor = _any(
        name,
        (
            "corporation tax payable",
            "corporation tax creditor",
            "corporation tax liability",
            "corporation tax provision",
            "corp tax payable",
        ),
    )
    if charge and creditor:
        return None
    if charge:
        return SublineHit("TAX_CHARGE", 40)
    if creditor:
        return SublineHit("CORP_TAX", 40)
    return None


def _depreciation_charge(name: str) -> bool:
    return _any(
        name,
        (
            "depreciation charge",
            "depreciation expense",
            "charge for depreciation",
            "depreciation for the year",
        ),
    )


def _depreciation(name: str) -> SublineHit | None:
    if _amort_name(name):
        return None
    rou = _any(name, ("right-of-use", "right of use"))
    if rou and _accumulated_depreciation(name):
        return None
    if _accumulated_depreciation(name):
        return SublineHit("FA_ACCUM_DEP", 40)
    if _depreciation_charge(name):
        return SublineHit("DEPRECIATION_CHARGE", 40)
    return None


def _accumulated_amortisation(name: str) -> bool:
    return _any(
        name,
        (
            "accumulated amortisation",
            "accumulated amortization",
            "provision for amortisation",
            "provision for amortization",
            "amortisation brought forward",
            "amortization brought forward",
        ),
    )


def _amortisation_charge(name: str) -> bool:
    return _any(
        name,
        (
            "amortisation charge",
            "amortization charge",
            "amortisation expense",
            "amortization expense",
            "amortisation for the year",
            "amortization for the year",
            "charge for amortisation",
            "charge for amortization",
        ),
    )


def _amortisation(name: str) -> SublineHit | None:
    if _accumulated_amortisation(name) and _amortisation_charge(name):
        return None
    if _accumulated_amortisation(name):
        return SublineHit("FA_INTANGIBLE_AMORT", 40)
    if _amortisation_charge(name):
        return SublineHit("AMORTISATION_CHARGE", 40)
    return None


def _intangible_assets(name: str) -> SublineHit | None:
    if _accumulated_amortisation(name):
        return SublineHit("FA_INTANGIBLE_AMORT", 40)
    if _amortisation_charge(name):
        return None
    return _best(
        name,
        (
            (
                ("development costs", "development expenditure"),
                "FA_INTANGIBLE_COST",
                40,
                lambda text: _any(text, ("business development", "staff development", "training")),
            ),
            (
                ("goodwill", "patents", "patent", "trade marks", "trademarks", "trademark", "trade mark", "concessions", "concession"),
                "FA_INTANGIBLE_COST",
                40,
                _accumulated_amortisation,
            ),
            (
                ("licences", "licenses", "licence", "license"),
                "FA_INTANGIBLE_COST",
                35,
                lambda text: _any(text, ("fee", "fees", "subscription", "annual")),
            ),
            (
                ("computer software", "software"),
                "FA_INTANGIBLE_COST",
                35,
                lambda text: _has(text, "subscription"),
            ),
        ),
    )
