"""Statement builder — SOPL, SOFP, and SOCIE from mapped trial-balance accounts.

Subtotals are computed in Python with Decimal only. Period-end SOFP
retained_earnings and total_equity use SOCIE closing RE (opening RE from the
current TB + profit for period − dividends). Opening RE is never defaulted to
zero when no prior-period TB was uploaded — prior TBs are validator Check 3 only.

:func:`compute_net_profit` is the shared P&L profit function used by SOPL
net_profit, SOCIE profit_for_period, and validator Check 3 / Check 4.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence, TypeVar

# Credit-normal P&L / SOFP equity & liability lines: statement amount = -net_balance.
# Debit-normal asset / expense / dividend lines: statement amount = net_balance.

_FaceLineT = TypeVar("_FaceLineT")


class StatementAccount(Protocol):
    """Mapped TB account with evidence-graph identity."""

    id: uuid.UUID
    account_code: str
    net_balance: Decimal
    canonical_line: str


@dataclass(frozen=True)
class MappedStatementAccount:
    """Concrete input for statement building."""

    id: uuid.UUID
    account_code: str
    net_balance: Decimal
    canonical_line: str


@dataclass(frozen=True)
class StatementLineItemRecord:
    """statement_line_items-ready row (Product Spec §9.1), minus statement FK."""

    line_item_code: str
    line_item_name: str
    amount: Decimal
    is_subtotal: bool
    display_order: int
    source_account_ids: list[uuid.UUID]


class SocieSofpEquityMismatchError(Exception):
    """SOCIE total_equity_closing does not equal SOFP total_equity."""

    def __init__(self, socie_total: Decimal, sofp_total: Decimal) -> None:
        self.socie_total = socie_total
        self.sofp_total = sofp_total
        super().__init__(
            f"SOCIE total_equity_closing ({socie_total}) does not equal "
            f"SOFP total_equity ({sofp_total}). Difference: "
            f"{abs(socie_total - sofp_total)}"
        )


LINE_ITEM_NAMES: dict[str, str] = {
    "revenue": "Revenue",
    "cost_of_sales": "Cost of sales",
    "gross_profit": "Gross profit",
    "operating_expenses": "Operating expenses",
    "depreciation": "Depreciation",
    "amortisation": "Amortisation",
    "operating_profit": "Operating profit",
    "interest_income": "Interest income",
    "interest_expense": "Interest expense",
    "profit_before_tax": "Profit before tax",
    "tax": "Tax",
    "net_profit": "Net profit",
    "property_plant_equipment": "Property, plant and equipment",
    "intangible_assets": "Intangible assets",
    "investments": "Investments",
    "inventory": "Inventory",
    "trade_receivables": "Trade receivables",
    "prepayments": "Prepayments",
    "accrued_income": "Accrued income",
    "cash": "Cash",
    "non_current_assets": "Non-current assets",
    "current_assets": "Current assets",
    "total_assets": "Total assets",
    "trade_payables": "Trade payables",
    "provisions": "Provisions",
    "accruals": "Accruals",
    "deferred_income": "Deferred income",
    "taxes_payable": "Taxes payable",
    "social_security_payable": "Social security payable",
    "loans": "Loans",
    "non_current_liabilities": "Non-current liabilities",
    "current_liabilities": "Current liabilities",
    "total_liabilities": "Total liabilities",
    "share_capital": "Share capital",
    "share_premium": "Share premium",
    "retained_earnings": "Retained earnings",
    "revaluation_reserve": "Revaluation reserve",
    "dividends": "Dividends",
    "total_equity": "Total equity",
    "retained_earnings_opening": "Retained earnings (opening)",
    "profit_for_period": "Profit for the period",
    "retained_earnings_closing": "Retained earnings (closing)",
    "total_equity_closing": "Total equity (closing)",
}

# Debit-normal on the face of the statement (amount = net_balance).
_DEBIT_NORMAL_LINES: frozenset[str] = frozenset(
    {
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
        "amortisation",
        "interest_expense",
        "tax",
        "property_plant_equipment",
        "intangible_assets",
        "investments",
        "inventory",
        "trade_receivables",
        "prepayments",
        "accrued_income",
        "cash",
        "dividends",
    }
)

# P&L canonical lines that form SOPL net_profit / SOCIE profit_for_period.
# Shared with validator.py Check 3 and Check 4 — do not diverge.
PROFIT_AND_LOSS_LINES: frozenset[str] = frozenset(
    {
        "revenue",
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
        "amortisation",
        "interest_income",
        "interest_expense",
        "tax",
    }
)


class NetProfitAccount(Protocol):
    """Minimal account shape for :func:`compute_net_profit`."""

    net_balance: Decimal
    canonical_line: str


def compute_net_profit(accounts: Sequence[NetProfitAccount]) -> Decimal:
    """SOPL net profit from mapped P&L accounts (Decimal only).

    Equivalent to:
    revenue − cost_of_sales − operating_expenses − depreciation − amortisation
    + interest_income − interest_expense − tax.

    Sign convention: credit-normal lines contribute ``-net_balance``;
    debit-normal expense/tax lines also contribute ``-net_balance`` (a debit
    expense has positive net_balance and therefore reduces profit).
    """
    total = sum(
        (
            -account.net_balance
            for account in accounts
            if account.canonical_line in PROFIT_AND_LOSS_LINES
        ),
        Decimal("0"),
    )
    return total.quantize(Decimal("0.01"))


def pnl_source_account_ids(accounts: Sequence[StatementAccount]) -> list[uuid.UUID]:
    """Evidence-graph ids for accounts that feed :func:`compute_net_profit`."""
    return [
        account.id
        for account in accounts
        if account.canonical_line in PROFIT_AND_LOSS_LINES
    ]


# SOFP current / non-current classification (hardcoded defaults — no schema field).
#
# Caveat: ``loans`` defaults to non-current and ``provisions`` to current (most
# common SME presentation). Mixed-maturity loans or non-current provisions will
# be mis-classified until a future per-mapping / per-company override exists.
# ``investments`` defaults to non-current for the same reason.
SOFP_NON_CURRENT_ASSET_ORDER: tuple[str, ...] = (
    "property_plant_equipment",
    "intangible_assets",
    "investments",
)
SOFP_CURRENT_ASSET_ORDER: tuple[str, ...] = (
    "inventory",
    "trade_receivables",
    "prepayments",
    "accrued_income",
    "cash",
)
SOFP_NON_CURRENT_LIABILITY_ORDER: tuple[str, ...] = ("loans",)
SOFP_CURRENT_LIABILITY_ORDER: tuple[str, ...] = (
    "trade_payables",
    "provisions",
    "accruals",
    "deferred_income",
    "taxes_payable",
    "social_security_payable",
)

# Flat concatenations — face order is NC then current within assets/liabilities.
SOFP_ASSET_ORDER: tuple[str, ...] = (
    SOFP_NON_CURRENT_ASSET_ORDER + SOFP_CURRENT_ASSET_ORDER
)
SOFP_LIABILITY_ORDER: tuple[str, ...] = (
    SOFP_NON_CURRENT_LIABILITY_ORDER + SOFP_CURRENT_LIABILITY_ORDER
)

# total_equity = share_capital + share_premium + retained_earnings + revaluation_reserve.
SOFP_EQUITY_TOTAL_LINES: frozenset[str] = frozenset(
    {
        "share_capital",
        "share_premium",
        "retained_earnings",
        "revaluation_reserve",
    }
)

# Display-only nil face filter (does not change totals or underlying TB/mappings).
_NIL_FACE_TOLERANCE = Decimal("0.01")

# Always shown even at €0 — SOFP/SOCIE grands and SOPL cascade / SOCIE RE closing.
FACE_GRAND_TOTAL_CODES: frozenset[str] = frozenset(
    {
        "total_assets",
        "total_liabilities",
        "total_equity",
        "total_equity_closing",
        "net_profit",
    }
)
FACE_ALWAYS_KEEP_SUBTOTAL_CODES: frozenset[str] = FACE_GRAND_TOTAL_CODES | frozenset(
    {
        "gross_profit",
        "operating_profit",
        "profit_before_tax",
        "retained_earnings_closing",
    }
)

# SOFP section subtotals — omit when every leaf in the section was nil-filtered.
SOFP_SECTION_SUBTOTAL_LEAVES: dict[str, frozenset[str]] = {
    "non_current_assets": frozenset(SOFP_NON_CURRENT_ASSET_ORDER),
    "current_assets": frozenset(SOFP_CURRENT_ASSET_ORDER),
    "non_current_liabilities": frozenset(SOFP_NON_CURRENT_LIABILITY_ORDER),
    "current_liabilities": frozenset(SOFP_CURRENT_LIABILITY_ORDER),
}


def build_sopl(accounts: Sequence[StatementAccount]) -> list[StatementLineItemRecord]:
    """Build Statement of Profit or Loss line items in display order."""
    grouped = _group_accounts(accounts)
    lines: list[StatementLineItemRecord] = []
    order = 1

    revenue = _leaf_line("revenue", grouped, order)
    order += 1
    lines.append(revenue)

    cost_of_sales = _leaf_line("cost_of_sales", grouped, order)
    order += 1
    lines.append(cost_of_sales)

    gross_profit_amount = revenue.amount - cost_of_sales.amount
    gross_profit_ids = _merge_ids(revenue.source_account_ids, cost_of_sales.source_account_ids)
    lines.append(
        _subtotal_line("gross_profit", gross_profit_amount, order, gross_profit_ids)
    )
    order += 1

    operating_expenses = _leaf_line("operating_expenses", grouped, order)
    order += 1
    lines.append(operating_expenses)

    depreciation = _leaf_line("depreciation", grouped, order)
    order += 1
    lines.append(depreciation)

    amortisation = _leaf_line("amortisation", grouped, order)
    order += 1
    lines.append(amortisation)

    operating_profit_amount = (
        gross_profit_amount
        - operating_expenses.amount
        - depreciation.amount
        - amortisation.amount
    )
    operating_profit_ids = _merge_ids(
        gross_profit_ids,
        operating_expenses.source_account_ids,
        depreciation.source_account_ids,
        amortisation.source_account_ids,
    )
    lines.append(
        _subtotal_line(
            "operating_profit", operating_profit_amount, order, operating_profit_ids
        )
    )
    order += 1

    interest_income = _leaf_line("interest_income", grouped, order)
    order += 1
    lines.append(interest_income)

    interest_expense = _leaf_line("interest_expense", grouped, order)
    order += 1
    lines.append(interest_expense)

    profit_before_tax_amount = (
        operating_profit_amount + interest_income.amount - interest_expense.amount
    )
    profit_before_tax_ids = _merge_ids(
        operating_profit_ids,
        interest_income.source_account_ids,
        interest_expense.source_account_ids,
    )
    lines.append(
        _subtotal_line(
            "profit_before_tax", profit_before_tax_amount, order, profit_before_tax_ids
        )
    )
    order += 1

    tax = _leaf_line("tax", grouped, order)
    order += 1
    lines.append(tax)

    net_profit_amount = compute_net_profit(accounts)
    net_profit_ids = pnl_source_account_ids(accounts)
    lines.append(_subtotal_line("net_profit", net_profit_amount, order, net_profit_ids))

    return lines


def build_sofp(
    accounts: Sequence[StatementAccount],
    *,
    retained_earnings_closing: Decimal,
    retained_earnings_source_ids: Sequence[uuid.UUID],
) -> list[StatementLineItemRecord]:
    """Build Statement of Financial Position line items in display order.

    Assets and liabilities are segmented into non-current / current groups with
    section subtotals, then grand totals (see ``SOFP_NON_CURRENT_*`` /
    ``SOFP_CURRENT_*`` order tuples and the classification caveat there).

    The retained_earnings face line and total_equity always use the supplied
    period-end closing balance (typically from :func:`_compute_socie_rollforward`).
    Callers must pass an explicit closing RE — there is no raw-TB default.
    """
    grouped = _group_accounts(accounts)
    lines: list[StatementLineItemRecord] = []
    order = 1

    non_current_assets, order = _append_sofp_leaf_group(
        lines, grouped, SOFP_NON_CURRENT_ASSET_ORDER, order
    )
    lines.append(
        _subtotal_line(
            "non_current_assets",
            sum((line.amount for line in non_current_assets), Decimal("0")),
            order,
            _merge_ids(*(line.source_account_ids for line in non_current_assets)),
        )
    )
    order += 1

    current_assets, order = _append_sofp_leaf_group(
        lines, grouped, SOFP_CURRENT_ASSET_ORDER, order
    )
    lines.append(
        _subtotal_line(
            "current_assets",
            sum((line.amount for line in current_assets), Decimal("0")),
            order,
            _merge_ids(*(line.source_account_ids for line in current_assets)),
        )
    )
    order += 1

    asset_lines = non_current_assets + current_assets
    total_assets_amount = sum((line.amount for line in asset_lines), Decimal("0"))
    total_assets_ids = _merge_ids(*(line.source_account_ids for line in asset_lines))
    lines.append(
        _subtotal_line("total_assets", total_assets_amount, order, total_assets_ids)
    )
    order += 1

    non_current_liabilities, order = _append_sofp_leaf_group(
        lines, grouped, SOFP_NON_CURRENT_LIABILITY_ORDER, order
    )
    lines.append(
        _subtotal_line(
            "non_current_liabilities",
            sum((line.amount for line in non_current_liabilities), Decimal("0")),
            order,
            _merge_ids(*(line.source_account_ids for line in non_current_liabilities)),
        )
    )
    order += 1

    current_liabilities, order = _append_sofp_leaf_group(
        lines, grouped, SOFP_CURRENT_LIABILITY_ORDER, order
    )
    lines.append(
        _subtotal_line(
            "current_liabilities",
            sum((line.amount for line in current_liabilities), Decimal("0")),
            order,
            _merge_ids(*(line.source_account_ids for line in current_liabilities)),
        )
    )
    order += 1

    liability_lines = non_current_liabilities + current_liabilities
    total_liabilities_amount = sum((line.amount for line in liability_lines), Decimal("0"))
    total_liabilities_ids = _merge_ids(
        *(line.source_account_ids for line in liability_lines)
    )
    lines.append(
        _subtotal_line(
            "total_liabilities", total_liabilities_amount, order, total_liabilities_ids
        )
    )
    order += 1

    share_capital = _leaf_line("share_capital", grouped, order)
    order += 1
    lines.append(share_capital)

    share_premium = _leaf_line("share_premium", grouped, order)
    order += 1
    lines.append(share_premium)

    re_ids = list(retained_earnings_source_ids)
    retained_earnings = StatementLineItemRecord(
        line_item_code="retained_earnings",
        line_item_name=LINE_ITEM_NAMES["retained_earnings"],
        amount=_quantize(retained_earnings_closing),
        is_subtotal=False,
        display_order=order,
        source_account_ids=re_ids,
    )
    order += 1
    lines.append(retained_earnings)

    revaluation_reserve = _leaf_line("revaluation_reserve", grouped, order)
    order += 1
    lines.append(revaluation_reserve)

    dividends = _leaf_line("dividends", grouped, order)
    order += 1
    lines.append(dividends)

    # Must match validator.py net_assets / EQUITY_LINES_SOFP: SC + SP + RE + RR.
    total_equity_amount = (
        share_capital.amount
        + share_premium.amount
        + retained_earnings.amount
        + revaluation_reserve.amount
    )
    total_equity_ids = _merge_ids(
        share_capital.source_account_ids,
        share_premium.source_account_ids,
        retained_earnings.source_account_ids,
        revaluation_reserve.source_account_ids,
    )
    lines.append(
        _subtotal_line("total_equity", total_equity_amount, order, total_equity_ids)
    )

    return lines


def build_statements(
    accounts: Sequence[StatementAccount],
) -> tuple[
    list[StatementLineItemRecord],
    list[StatementLineItemRecord],
    list[StatementLineItemRecord],
]:
    """Build SOPL, SOFP, and SOCIE with period-end closing retained earnings on SOFP."""
    sopl_lines = build_sopl(accounts)
    rollforward = _compute_socie_rollforward(accounts)
    sofp_lines = build_sofp(
        accounts,
        retained_earnings_closing=rollforward.retained_earnings_closing_amount,
        retained_earnings_source_ids=rollforward.retained_earnings_closing_ids,
    )
    socie_lines = build_socie(
        accounts,
        sopl_lines=sopl_lines,
        sofp_lines=sofp_lines,
        rollforward=rollforward,
    )
    return sopl_lines, sofp_lines, socie_lines


@dataclass(frozen=True)
class _SocieRollforward:
    opening_amount: Decimal
    opening_ids: list[uuid.UUID]
    profit_amount: Decimal
    profit_ids: list[uuid.UUID]
    dividends_amount: Decimal
    dividends_ids: list[uuid.UUID]
    share_capital_amount: Decimal
    share_capital_ids: list[uuid.UUID]
    retained_earnings_closing_amount: Decimal
    retained_earnings_closing_ids: list[uuid.UUID]
    total_equity_closing_amount: Decimal
    total_equity_closing_ids: list[uuid.UUID]


def build_socie(
    accounts: Sequence[StatementAccount],
    *,
    sopl_lines: Sequence[StatementLineItemRecord],
    sofp_lines: Sequence[StatementLineItemRecord],
    rollforward: _SocieRollforward | None = None,
) -> list[StatementLineItemRecord]:
    """Build Statement of Changes in Equity line items in display order.

    Opening retained earnings come from the current TB's retained_earnings account.
    Raises SocieSofpEquityMismatchError if SOCIE total_equity_closing does not
    exactly equal SOFP total_equity from the same run.
    """
    sofp_by_code = {line.line_item_code: line for line in sofp_lines}
    try:
        sofp_total_equity = sofp_by_code["total_equity"]
    except KeyError as exc:
        raise ValueError(
            f"SOCIE requires SOFP total_equity line; missing {exc.args[0]!r}"
        ) from exc

    if rollforward is None:
        rollforward = _compute_socie_rollforward(accounts)

    # sopl_lines may be passed for callers that already built SOPL; profit always
    # comes from compute_net_profit so it cannot drift from validator Check 4.
    if sopl_lines:
        sopl_by_code = {line.line_item_code: line for line in sopl_lines}
        sopl_profit_line = sopl_by_code.get("net_profit")
        if (
            sopl_profit_line is not None
            and sopl_profit_line.amount != rollforward.profit_amount
        ):
            raise ValueError(
                f"SOPL net_profit ({sopl_profit_line.amount}) disagrees with "
                f"compute_net_profit ({rollforward.profit_amount})"
            )

    opening_amount = rollforward.opening_amount
    opening_ids = rollforward.opening_ids
    profit_amount = rollforward.profit_amount
    profit_ids = rollforward.profit_ids
    dividends_amount = rollforward.dividends_amount
    dividends_ids = rollforward.dividends_ids
    share_capital_amount = rollforward.share_capital_amount
    share_capital_ids = rollforward.share_capital_ids
    retained_earnings_closing_amount = rollforward.retained_earnings_closing_amount
    retained_earnings_closing_ids = rollforward.retained_earnings_closing_ids
    total_equity_closing_amount = rollforward.total_equity_closing_amount
    total_equity_closing_ids = rollforward.total_equity_closing_ids

    if total_equity_closing_amount != sofp_total_equity.amount:
        raise SocieSofpEquityMismatchError(
            total_equity_closing_amount,
            sofp_total_equity.amount,
        )

    lines: list[StatementLineItemRecord] = []
    order = 1

    lines.append(
        StatementLineItemRecord(
            line_item_code="retained_earnings_opening",
            line_item_name=LINE_ITEM_NAMES["retained_earnings_opening"],
            amount=_quantize(opening_amount),
            is_subtotal=False,
            display_order=order,
            source_account_ids=opening_ids,
        )
    )
    order += 1

    lines.append(
        StatementLineItemRecord(
            line_item_code="profit_for_period",
            line_item_name=LINE_ITEM_NAMES["profit_for_period"],
            amount=_quantize(profit_amount),
            is_subtotal=False,
            display_order=order,
            source_account_ids=profit_ids,
        )
    )
    order += 1

    lines.append(
        StatementLineItemRecord(
            line_item_code="dividends",
            line_item_name=LINE_ITEM_NAMES["dividends"],
            amount=_quantize(dividends_amount),
            is_subtotal=False,
            display_order=order,
            source_account_ids=dividends_ids,
        )
    )
    order += 1

    lines.append(
        _subtotal_line(
            "retained_earnings_closing",
            retained_earnings_closing_amount,
            order,
            retained_earnings_closing_ids,
        )
    )
    order += 1

    lines.append(
        StatementLineItemRecord(
            line_item_code="share_capital",
            line_item_name=LINE_ITEM_NAMES["share_capital"],
            amount=_quantize(share_capital_amount),
            is_subtotal=False,
            display_order=order,
            source_account_ids=share_capital_ids,
        )
    )
    order += 1

    lines.append(
        _subtotal_line(
            "total_equity_closing",
            total_equity_closing_amount,
            order,
            total_equity_closing_ids,
        )
    )

    return lines


def _compute_socie_rollforward(
    accounts: Sequence[StatementAccount],
    sopl_lines: Sequence[StatementLineItemRecord] | None = None,
) -> _SocieRollforward:
    """Roll-forward opening RE using shared :func:`compute_net_profit`.

    *sopl_lines* is accepted for API compatibility with callers that already
    built SOPL; profit is always taken from the shared function, not from the
    SOPL line list, so validator and SOCIE cannot drift.
    """
    del sopl_lines  # profit comes from compute_net_profit, not SOPL lines
    grouped = _group_accounts(accounts)

    opening_amount, opening_ids = _sum_line("retained_earnings", grouped)
    profit_amount = compute_net_profit(accounts)
    profit_ids = pnl_source_account_ids(accounts)
    dividends_amount, dividends_ids = _sum_line("dividends", grouped)
    share_capital_amount, share_capital_ids = _sum_line("share_capital", grouped)
    share_premium_amount, share_premium_ids = _sum_line("share_premium", grouped)
    revaluation_reserve_amount, revaluation_reserve_ids = _sum_line(
        "revaluation_reserve", grouped
    )

    retained_earnings_closing_amount = (
        opening_amount + profit_amount - dividends_amount
    )
    retained_earnings_closing_ids = _merge_ids(opening_ids, profit_ids, dividends_ids)

    # Must match build_sofp total_equity: SC + SP + closing RE + RR (excludes dividends).
    total_equity_closing_amount = (
        share_capital_amount
        + share_premium_amount
        + retained_earnings_closing_amount
        + revaluation_reserve_amount
    )
    total_equity_closing_ids = _merge_ids(
        share_capital_ids,
        share_premium_ids,
        retained_earnings_closing_ids,
        revaluation_reserve_ids,
    )

    return _SocieRollforward(
        opening_amount=opening_amount,
        opening_ids=opening_ids,
        profit_amount=profit_amount,
        profit_ids=profit_ids,
        dividends_amount=dividends_amount,
        dividends_ids=dividends_ids,
        share_capital_amount=share_capital_amount,
        share_capital_ids=share_capital_ids,
        retained_earnings_closing_amount=retained_earnings_closing_amount,
        retained_earnings_closing_ids=retained_earnings_closing_ids,
        total_equity_closing_amount=total_equity_closing_amount,
        total_equity_closing_ids=total_equity_closing_ids,
    )


def iter_nil_filtered_face_lines(
    lines: Sequence[_FaceLineT],
) -> list[_FaceLineT]:
    """Return face rows with nil leaves (and empty SOFP section subtots) removed.

    Works on any object with ``line_item_code``, ``amount``, and ``is_subtotal``
    (builder records or ORM ``StatementLineItem``). Does not mutate inputs.
    """

    def _is_nil(amount: Decimal) -> bool:
        return abs(Decimal(amount)) <= _NIL_FACE_TOLERANCE

    kept_leaf_codes = {
        line.line_item_code  # type: ignore[attr-defined]
        for line in lines
        if not line.is_subtotal and not _is_nil(line.amount)  # type: ignore[attr-defined]
    }

    filtered: list[_FaceLineT] = []
    for line in lines:
        if line.is_subtotal:  # type: ignore[attr-defined]
            code = line.line_item_code  # type: ignore[attr-defined]
            if code in FACE_ALWAYS_KEEP_SUBTOTAL_CODES:
                filtered.append(line)
                continue
            section_leaves = SOFP_SECTION_SUBTOTAL_LEAVES.get(code)
            if section_leaves is not None:
                if kept_leaf_codes & section_leaves:
                    filtered.append(line)
                continue
            filtered.append(line)
            continue
        if not _is_nil(line.amount):  # type: ignore[attr-defined]
            filtered.append(line)
    return filtered


def filter_nil_face_lines(
    lines: Sequence[StatementLineItemRecord],
) -> list[StatementLineItemRecord]:
    """Display-only: omit nil leaves / empty SOFP sections; renumber display_order.

    Used by export load (and tests). Builders persist the full unfiltered skeleton;
    GET and POST generate/regenerate responses use ``iter_nil_filtered_face_lines``
    the same way. Totals are unchanged because nil leaves already contributed €0.
    """
    filtered = iter_nil_filtered_face_lines(lines)
    return [
        StatementLineItemRecord(
            line_item_code=line.line_item_code,
            line_item_name=line.line_item_name,
            amount=line.amount,
            is_subtotal=line.is_subtotal,
            display_order=index,
            source_account_ids=line.source_account_ids,
        )
        for index, line in enumerate(filtered, start=1)
    ]


def _append_sofp_leaf_group(
    lines: list[StatementLineItemRecord],
    grouped: dict[str, list[StatementAccount]],
    codes: Sequence[str],
    order: int,
) -> tuple[list[StatementLineItemRecord], int]:
    """Append leaf face lines for ``codes``; return the new leaves and next order."""
    group: list[StatementLineItemRecord] = []
    for code in codes:
        line = _leaf_line(code, grouped, order)
        order += 1
        group.append(line)
        lines.append(line)
    return group, order


def _group_accounts(
    accounts: Sequence[StatementAccount],
) -> dict[str, list[StatementAccount]]:
    grouped: dict[str, list[StatementAccount]] = {}
    for account in accounts:
        grouped.setdefault(account.canonical_line, []).append(account)
    return grouped


def _statement_amount(canonical_line: str, net_balance: Decimal) -> Decimal:
    if canonical_line in _DEBIT_NORMAL_LINES:
        return net_balance
    return -net_balance


def _sum_line(
    canonical_line: str,
    grouped: dict[str, list[StatementAccount]],
) -> tuple[Decimal, list[uuid.UUID]]:
    members = grouped.get(canonical_line, [])
    amount = sum(
        (_statement_amount(canonical_line, account.net_balance) for account in members),
        Decimal("0"),
    )
    ids = [account.id for account in members]
    return _quantize(amount), ids


def _leaf_line(
    canonical_line: str,
    grouped: dict[str, list[StatementAccount]],
    display_order: int,
) -> StatementLineItemRecord:
    amount, source_ids = _sum_line(canonical_line, grouped)
    return StatementLineItemRecord(
        line_item_code=canonical_line,
        line_item_name=LINE_ITEM_NAMES[canonical_line],
        amount=amount,
        is_subtotal=False,
        display_order=display_order,
        source_account_ids=source_ids,
    )


def _subtotal_line(
    code: str,
    amount: Decimal,
    display_order: int,
    source_account_ids: list[uuid.UUID],
) -> StatementLineItemRecord:
    return StatementLineItemRecord(
        line_item_code=code,
        line_item_name=LINE_ITEM_NAMES[code],
        amount=_quantize(amount),
        is_subtotal=True,
        display_order=display_order,
        source_account_ids=list(source_account_ids),
    )


def _merge_ids(*groups: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    seen: set[uuid.UUID] = set()
    merged: list[uuid.UUID] = []
    for group in groups:
        for account_id in group:
            if account_id not in seen:
                seen.add(account_id)
                merged.append(account_id)
    return merged


def _quantize(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("0.01"))
