"""Statement builder — SOPL and SOFP from mapped trial-balance accounts.

SOCIE is intentionally out of scope here. Subtotals are computed in Python with
Decimal only. SOFP total_equity uses Share Capital + Retained Earnings and
excludes open Dividends, matching validator.py Check 4 / Product Spec §4.2.1.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, Sequence

# Credit-normal P&L / SOFP equity & liability lines: statement amount = -net_balance.
# Debit-normal asset / expense / dividend lines: statement amount = net_balance.


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


LINE_ITEM_NAMES: dict[str, str] = {
    "revenue": "Revenue",
    "cost_of_sales": "Cost of sales",
    "gross_profit": "Gross profit",
    "operating_expenses": "Operating expenses",
    "depreciation": "Depreciation",
    "operating_profit": "Operating profit",
    "interest_income": "Interest income",
    "interest_expense": "Interest expense",
    "profit_before_tax": "Profit before tax",
    "tax": "Tax",
    "net_profit": "Net profit",
    "property_plant_equipment": "Property, plant and equipment",
    "intangible_assets": "Intangible assets",
    "inventory": "Inventory",
    "trade_receivables": "Trade receivables",
    "cash": "Cash",
    "total_assets": "Total assets",
    "trade_payables": "Trade payables",
    "accruals": "Accruals",
    "loans": "Loans",
    "total_liabilities": "Total liabilities",
    "share_capital": "Share capital",
    "retained_earnings": "Retained earnings",
    "dividends": "Dividends",
    "total_equity": "Total equity",
}

# Debit-normal on the face of the statement (amount = net_balance).
_DEBIT_NORMAL_LINES: frozenset[str] = frozenset(
    {
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
        "interest_expense",
        "tax",
        "property_plant_equipment",
        "intangible_assets",
        "inventory",
        "trade_receivables",
        "cash",
        "dividends",
    }
)

SOFP_ASSET_ORDER: tuple[str, ...] = (
    "property_plant_equipment",
    "intangible_assets",
    "inventory",
    "trade_receivables",
    "cash",
)

SOFP_LIABILITY_ORDER: tuple[str, ...] = (
    "trade_payables",
    "accruals",
    "loans",
)

# total_equity = share_capital + retained_earnings only (excludes dividends).
SOFP_EQUITY_TOTAL_LINES: frozenset[str] = frozenset(
    {
        "share_capital",
        "retained_earnings",
    }
)


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

    operating_profit_amount = (
        gross_profit_amount - operating_expenses.amount - depreciation.amount
    )
    operating_profit_ids = _merge_ids(
        gross_profit_ids,
        operating_expenses.source_account_ids,
        depreciation.source_account_ids,
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

    net_profit_amount = profit_before_tax_amount - tax.amount
    net_profit_ids = _merge_ids(profit_before_tax_ids, tax.source_account_ids)
    lines.append(_subtotal_line("net_profit", net_profit_amount, order, net_profit_ids))

    return lines


def build_sofp(accounts: Sequence[StatementAccount]) -> list[StatementLineItemRecord]:
    """Build Statement of Financial Position line items in display order."""
    grouped = _group_accounts(accounts)
    lines: list[StatementLineItemRecord] = []
    order = 1

    asset_lines: list[StatementLineItemRecord] = []
    for code in SOFP_ASSET_ORDER:
        line = _leaf_line(code, grouped, order)
        order += 1
        asset_lines.append(line)
        lines.append(line)

    total_assets_amount = sum((line.amount for line in asset_lines), Decimal("0"))
    total_assets_ids = _merge_ids(*(line.source_account_ids for line in asset_lines))
    lines.append(
        _subtotal_line("total_assets", total_assets_amount, order, total_assets_ids)
    )
    order += 1

    liability_lines: list[StatementLineItemRecord] = []
    for code in SOFP_LIABILITY_ORDER:
        line = _leaf_line(code, grouped, order)
        order += 1
        liability_lines.append(line)
        lines.append(line)

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

    retained_earnings = _leaf_line("retained_earnings", grouped, order)
    order += 1
    lines.append(retained_earnings)

    dividends = _leaf_line("dividends", grouped, order)
    order += 1
    lines.append(dividends)

    # Must match validator.py net_assets / EQUITY_LINES_SOFP: SC + RE only.
    total_equity_amount = share_capital.amount + retained_earnings.amount
    total_equity_ids = _merge_ids(
        share_capital.source_account_ids,
        retained_earnings.source_account_ids,
    )
    lines.append(
        _subtotal_line("total_equity", total_equity_amount, order, total_equity_ids)
    )

    return lines


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
