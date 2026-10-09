"""How a statutory draft is printed. Figures stay on the engine rows.

Cover, contents, and section toggles can insert or drop a block in the
section list. They should not reimplement amounts, dates, or the nil-line
filter that live here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from findraft.engine.rounding import round_to, rounding_gap

WHOLE_UNIT = Decimal("1")
_TOLERANCE = Decimal("0.01")
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}
_NAMES = {"EUR": "euro", "GBP": "pound sterling", "USD": "US dollar"}
# Report-setup rounding options. The unit word follows the company currency.
_ROUNDING_LABELS = {
    "EUR": ("Nearest euro", "Nearest €'000"),
    "GBP": ("Nearest pound", "Nearest £'000"),
    "USD": ("Nearest dollar", "Nearest $'000"),
}
_NEUTRAL_CURRENCY = "the company's functional currency"
_KEEP_ON_THE_FACE = frozenset(
    {"Net assets", "Total equity", "Profit for the financial year"}
)

# Child labels that must foot to the engine subtotal once they are rounded
# to a whole unit. The subtotal itself is still the engine figure.
_SOFP_GROUPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "Stocks",
            "Trade debtors",
            "Other debtors",
            "Cash at bank and in hand",
        ),
        "Total current assets",
    ),
    (
        (
            "Total current assets",
            "Creditors: amounts falling due within one year",
        ),
        "Net current assets",
    ),
    (
        (
            "Intangible assets",
            "Tangible assets",
            "Fixed asset investments",
            "Right-of-use assets",
            "Net current assets",
        ),
        "Total assets less current liabilities",
    ),
    (
        (
            "Total assets less current liabilities",
            "Lease liabilities",
            "Creditors: amounts falling due after more than one year",
            "Provisions for liabilities",
            "Deferred tax liability",
        ),
        "Net assets",
    ),
    (
        (
            "Called up share capital",
            "Share premium account",
            "Profit and loss account",
        ),
        "Total equity",
    ),
)
_INCOME_GROUPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("Turnover", "Cost of sales"), "Gross profit"),
    (
        (
            "Gross profit",
            "Distribution costs",
            "Administrative expenses (including depreciation)",
            "Other operating income",
        ),
        "Operating profit",
    ),
    (
        ("Operating profit", "Interest receivable", "Interest payable"),
        "Profit before tax",
    ),
    (("Profit before tax", "Tax on profit"), "Profit for the financial year"),
)
_GROUPS = {total: children for children, total in (*_SOFP_GROUPS, *_INCOME_GROUPS)}


class FaceRow(Protocol):
    @property
    def label(self) -> str: ...

    @property
    def current(self) -> Decimal: ...

    @property
    def prior(self) -> Decimal | None: ...


class NoteAmount(Protocol):
    @property
    def line(self) -> str: ...

    @property
    def current(self) -> Decimal: ...

    @property
    def prior(self) -> Decimal: ...


def parse_iso_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def format_date(value: date) -> str:
    """31 December 2026. The month names do not follow the process locale."""
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def format_iso_date(value: str) -> str:
    parsed = parse_iso_date(value)
    if parsed is None:
        return value.strip()
    return format_date(parsed)


def is_twelve_months(start: date, end: date) -> bool:
    """True when end is the day before the anniversary of start."""
    try:
        anniversary = start.replace(year=start.year + 1)
    except ValueError:
        anniversary = date(start.year + 1, 3, 1)
    return end == anniversary - timedelta(days=1)


def statement_period_phrase(start: date | None, end: date | None) -> str:
    """Twelve months is a year. Any other length names the start and the end."""
    if end is None:
        return ""
    if start is not None and not is_twelve_months(start, end):
        return f"for the period from {format_date(start)} to {format_date(end)}"
    return f"for the year ended {format_date(end)}"


def as_at_phrase(end: date | None) -> str:
    if end is None:
        return ""
    return f"as at {format_date(end)}"


def currency_symbol(code: str) -> str:
    """Symbol for a known currency. An unknown code is printed as itself."""
    cleaned = code.strip().upper()
    if not cleaned:
        return ""
    return _SYMBOLS.get(cleaned, cleaned)


def currency_name_for_policy(code: str) -> str:
    """euro, pound sterling, or US dollar. Otherwise a neutral phrase."""
    cleaned = code.strip().upper()
    return _NAMES.get(cleaned, _NEUTRAL_CURRENCY)


def rounding_labels(code: str) -> tuple[str, str]:
    """Unit and thousands labels for the report-setup rounding control."""
    cleaned = code.strip().upper()
    known = _ROUNDING_LABELS.get(cleaned)
    if known is not None:
        return known
    if not cleaned:
        return ("Nearest unit", "Nearest '000")
    return (f"Nearest {cleaned}", f"Nearest {cleaned}'000")


def format_whole(value: Decimal) -> str:
    """Whole units, comma grouping, brackets for a negative. No currency symbol."""
    rounded = round_to(value, WHOLE_UNIT)
    text = f"{abs(rounded):,}"
    if rounded < 0:
        return f"({text})"
    return text


def format_whole_prose(value: Decimal, currency_code: str) -> str:
    """A symbol sits with the amount in a sentence, not in a column heading."""
    symbol = currency_symbol(currency_code)
    amount = format_whole(value)
    if not symbol:
        return amount
    if amount.startswith("("):
        return f"({symbol}{amount[1:]}"
    return f"{symbol}{amount}"


def column_headings(
    *,
    period_end: date | None,
    currency_code: str,
    comparative: bool,
) -> list[str]:
    """Year and symbol. A first period has one column."""
    symbol = currency_symbol(currency_code)
    if period_end is None:
        current = f"Current {symbol}".strip()
        prior = f"Prior {symbol}".strip()
    else:
        current = f"{period_end.year} {symbol}".strip()
        prior = f"{period_end.year - 1} {symbol}".strip()
    if comparative:
        return [current, prior]
    return [current]


def _nil(value: Decimal | None) -> bool:
    return value is None or abs(value) <= _TOLERANCE


def _keep(row: FaceRow, *, comparative: bool) -> bool:
    if row.label in _KEEP_ON_THE_FACE:
        return True
    if not comparative:
        return not _nil(row.current)
    return not (_nil(row.current) and _nil(row.prior))


def _amounts(current: Decimal, prior: Decimal | None, *, comparative: bool) -> list[str]:
    shown = [format_whole(current)]
    if comparative:
        shown.append("" if prior is None else format_whole(prior))
    return shown


def _difference(
    children: list[Decimal | None], total: Decimal | None
) -> Decimal | None:
    if total is None or any(item is None for item in children):
        return None
    gap = rounding_gap([item for item in children if item is not None], total, WHOLE_UNIT)
    if gap == 0:
        return None
    return -gap


def face_display_rows(
    rows: Sequence[FaceRow],
    *,
    comparative: bool,
) -> list[dict[str, object]]:
    """Printable face. Nil lines drop out. Engine rows are not changed.

    A rounding-difference row is inserted only when ``rounding_gap`` says the
    rounded children do not foot to the rounded subtotal.
    """
    by_label = {row.label: row for row in rows}
    printed: list[dict[str, object]] = []
    for row in rows:
        children = _GROUPS.get(row.label)
        if children is not None and _keep(row, comparative=comparative):
            if all(name in by_label for name in children):
                current_gap = _difference(
                    [by_label[name].current for name in children], row.current
                )
                prior_gap = (
                    _difference(
                        [by_label[name].prior for name in children], row.prior
                    )
                    if comparative
                    else None
                )
                if current_gap is not None or prior_gap is not None:
                    printed.append(
                        {
                            "label": "Rounding difference",
                            "amounts": _amounts(
                                current_gap or Decimal("0"),
                                None if prior_gap is None else prior_gap,
                                comparative=comparative,
                            ),
                        }
                    )
        if _keep(row, comparative=comparative):
            printed.append(
                {
                    "label": row.label,
                    "amounts": _amounts(row.current, row.prior, comparative=comparative),
                }
            )
    return printed


def note_display_lines(
    lines: Sequence[NoteAmount],
    *,
    comparative: bool,
) -> list[dict[str, object]]:
    """Note breakdown lines. A nil line in every presented year is omitted."""
    if not comparative:
        visible = [line for line in lines if not _nil(line.current)]
    else:
        visible = [
            line for line in lines if not (_nil(line.current) and _nil(line.prior))
        ]
    printed: list[dict[str, object]] = [
        {
            "line": line.line,
            "amounts": _amounts(line.current, line.prior, comparative=comparative),
        }
        for line in visible
    ]
    if not lines:
        return printed
    current_gap = _difference(
        [line.current for line in lines],
        sum((line.current for line in lines), Decimal("0")),
    )
    prior_gap = (
        _difference(
            [line.prior for line in lines],
            sum((line.prior for line in lines), Decimal("0")),
        )
        if comparative
        else None
    )
    if current_gap is not None or prior_gap is not None:
        printed.append(
            {
                "line": "Rounding difference",
                "amounts": _amounts(
                    current_gap or Decimal("0"),
                    None if prior_gap is None else prior_gap,
                    comparative=comparative,
                ),
            }
        )
    return printed
