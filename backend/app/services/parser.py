"""Trial balance file parser — pandas-based, Decimal-only arithmetic."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import BinaryIO, Literal

import openpyxl
import pandas as pd
from zipfile import BadZipFile

logger = logging.getLogger(__name__)

TOLERANCE = Decimal("0.01")
MIN_DATA_ROWS = 3
SCAN_CELL_LIMIT = 100

HEADER_FIRST_CELL_KEYWORDS = (
    "account",
    "code",
    "description",
    "debit",
    "credit",
    "balance",
    "currency",
    "name",
)
# NB: bare "balance" is intentionally excluded — it collides with real account
# names ("Opening Balance Equity", "Bank Balance"). Totals rows in a TB say "Total".
TOTALS_NAME_KEYWORDS = ("total", "subtotal", "sum")

# Headings match the whole cell after normalisation, not a substring.
# "Credit Limit", "Account Manager", and "Description of the amount" do not match.
_CODE_HEADERS = frozenset(
    {
        "account code",
        "account no",
        "account number",
        "acct code",
        "acc no",
        "a/c",
        "a/c no",
        "gl code",
        "nominal",
        "nominal code",
        "ledger code",
        "code",
    }
)
_NAME_HEADERS = frozenset(
    {
        "account name",
        "account description",
        "nominal name",
        "description",
        "particulars",
        "narrative",
        "name",
    }
)
# Bare "account" is the Xero/QuickBooks combined column. It is the name only
# when a separate code heading is already present.
_COMBINED_HEADERS = frozenset(
    {"gl account", "ledger account", "account title", "account"}
)
_DEBIT_HEADERS = frozenset({"debit", "debits", "dr"})
_CREDIT_HEADERS = frozenset({"credit", "credits", "cr"})
# A signed balance is safe only for these headings. Positive is debit and
# negative is credit, which is the same rule as before. A generic "Amount"
# column is not supported.
_BALANCE_HEADERS = frozenset({"balance", "net balance"})
_DATE_HEADERS = frozenset(
    {"date", "txn date", "transaction date", "posting date"}
)
_CURRENCY_HEADER_TAILS = frozenset({"gbp", "eur", "usd"})
_GL_ON_TB_MESSAGE = (
    "This looks like a general ledger, not a trial balance — "
    "try the General ledger option instead."
)

SYMBOL_TO_CURRENCY: dict[str, str] = {
    "£": "GBP",
    "€": "EUR",
    "$": "USD",
}
ISO_CURRENCIES = frozenset({"GBP", "EUR", "USD"})

TBFormat = Literal["four_column", "single_balance"]


@dataclass(frozen=True)
class TBRow:
    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    net_balance: Decimal
    currency: str
    row_index: int


class ParseError(Exception):
    """Raised when a cell cannot be parsed as a monetary value."""


PASSWORD_PROTECTED_MESSAGE = (
    "This file is password-protected — please remove the password and re-upload."
)


class PasswordProtectedError(ParseError):
    """Raised when an uploaded PDF/Excel file is encrypted / password-protected.

    Subclasses ParseError so existing upload handlers surface it, but carries the
    specific, actionable password message (distinct from a generic parse failure).
    """

    def __init__(self, message: str = PASSWORD_PROTECTED_MESSAGE) -> None:
        super().__init__(message)


# Compound File Binary / OLE2 signature. A normal .xlsx is a ZIP ("PK\x03\x04");
# a password-encrypted OOXML workbook is an OLE2 container starting with these
# 8 bytes (it wraps an "EncryptedPackage" stream). openpyxl then fails with
# BadZipFile, which we would otherwise report as a generic "not a valid workbook".
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def looks_like_encrypted_office(content: bytes) -> bool:
    """True when bytes carry the OLE2/CFB signature (encrypted OOXML or legacy Office)."""
    return content[:8] == _OLE2_MAGIC


def pdf_is_password_protected(content: bytes) -> bool:
    """True when the PDF requires a password to open (PyMuPDF ``needs_pass``)."""
    try:
        import fitz  # PyMuPDF
    except Exception:  # pragma: no cover - dependency always present in prod
        return False
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception:
        return False
    try:
        return bool(getattr(doc, "needs_pass", False))
    finally:
        doc.close()


class OrphanedAmountError(Exception):
    """Raised when a row has monetary values but no account identifiers."""

    def __init__(self, row_index: int, amount: Decimal, column_name: str) -> None:
        self.row_index = row_index
        self.amount = amount
        self.column_name = column_name
        super().__init__(
            f"Monetary value {amount} found at row {row_index} in column "
            f"{column_name!r} without an account code or account name."
        )


class AmbiguousCurrencyError(Exception):
    """Raised when multiple currency symbols are detected in the file."""

    def __init__(self, symbols: frozenset[str]) -> None:
        self.symbols = symbols
        symbol_list = ", ".join(sorted(symbols))
        super().__init__(
            f"Multiple currency symbols detected ({symbol_list}). "
            "Confirm currency in the upload UI before parsing proceeds."
        )


class UnbalancedTrialBalanceError(Exception):
    """Raised when total debits and credits differ beyond tolerance."""

    def __init__(self, total_debits: Decimal, total_credits: Decimal) -> None:
        self.total_debits = total_debits
        self.total_credits = total_credits
        self.difference = abs(total_debits - total_credits)
        super().__init__(
            f"Trial balance is unbalanced: total debits ({total_debits}) do not equal "
            f"total credits ({total_credits}). Difference: {self.difference}"
        )


def decimal_eq(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCE


def parse_monetary(
    value: object,
    *,
    row_index: int | None = None,
    column_name: str | None = None,
) -> Decimal:
    """Parse a monetary cell value into Decimal, never float."""
    if value is None:
        return Decimal("0")

    if isinstance(value, float) and pd.isna(value):
        return Decimal("0")

    text = str(value).strip()
    # Common ERP zero/empty representations.
    if text == "" or text.lower() in {"nan", "none", "nil", "n/a", "na", "--"}:
        return Decimal("0")

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()

    for symbol in SYMBOL_TO_CURRENCY:
        text = text.replace(symbol, "")
    text = text.replace(",", "").strip()

    # Trailing DR/CR sign convention (Sage / QuickBooks balance columns):
    # "1,000.00 CR" -> -1000 ; "1,000.00 DR" -> +1000. Applied before ISO-code
    # stripping so it is not mistaken for a currency suffix.
    upper = text.upper()
    if upper.endswith("CR") and any(ch.isdigit() for ch in text[:-2]):
        negative = not negative
        text = text[:-2].strip()
    elif upper.endswith("DR") and any(ch.isdigit() for ch in text[:-2]):
        text = text[:-2].strip()

    for code in ISO_CURRENCIES:
        if text.upper().endswith(code):
            text = text[: -len(code)].strip()

    if text in {"", "-"}:
        return Decimal("0")

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        location = _format_cell_location(row_index=row_index, column_name=column_name)
        raise ParseError(f"Non-numeric monetary value{location}: {value!r}") from exc

    return -amount if negative else amount


def _format_cell_location(
    *,
    row_index: int | None,
    column_name: str | None,
) -> str:
    if row_index is not None and column_name is not None:
        return f" at row {row_index}, column {column_name!r}"
    if row_index is not None:
        return f" at row {row_index}"
    if column_name is not None:
        return f" in column {column_name!r}"
    return ""


def parse_tb_file(
    file: BinaryIO | bytes,
    *,
    filename: str,
    functional_currency: str = "GBP",
) -> list[TBRow]:
    """Parse an uploaded .xlsx or .csv trial balance file into TBRow objects."""
    content = file if isinstance(file, bytes) else file.read()
    extension = filename.rsplit(".", 1)[-1].lower()

    if extension == "csv":
        dataframe = _read_csv(content)
        rows = _parse_dataframe(dataframe, functional_currency=functional_currency)
    elif extension == "xlsx":
        prepared = _prepare_xlsx(content)
        rows = _parse_xlsx(prepared, functional_currency=functional_currency)
    else:
        raise ParseError(f"Unsupported file type: {extension!r}. Expected .xlsx or .csv.")

    if not rows:
        raise ParseError(
            "No trial balance data rows found. The file appears to have headers only "
            "(or no account lines). Export a trial balance that includes account "
            "codes, names, and debit/credit amounts."
        )

    _validate_balanced(rows)
    return rows


def raise_if_ambiguous_currency_symbols(values: object) -> set[str]:
    """Scan cells for currency symbols; raise if more than one distinct symbol.

    Returns the set of symbols found (0 or 1 entries when it does not raise).
    Shared by the TB parser and GL → TB converter so both paths reject mixed
    £/€/$ symbols instead of silently stripping them into one currency.
    """
    symbols = _scan_currency_symbols_from_values(values)
    if len(symbols) > 1:
        logger.warning(
            "Ambiguous currency symbols detected in scanned cells: %s",
            ", ".join(sorted(symbols)),
        )
        raise AmbiguousCurrencyError(frozenset(symbols))
    return symbols


def _read_csv(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(
            BytesIO(content), header=None, dtype=str, keep_default_na=False
        )
    except pd.errors.EmptyDataError as exc:
        raise ParseError(
            "This CSV file is empty. Export a trial balance that includes account "
            "codes, names, and debit/credit amounts."
        ) from exc


def _prepare_xlsx(content: bytes) -> bytes:
    if looks_like_encrypted_office(content):
        raise PasswordProtectedError()
    try:
        workbook = openpyxl.load_workbook(BytesIO(content), data_only=True)
    except BadZipFile as exc:
        # An encrypted OOXML workbook is an OLE2 container, so openpyxl reports it
        # as "not a zip". Disambiguate password-protection from a genuinely broken
        # file so the user gets the actionable message.
        if looks_like_encrypted_office(content):
            raise PasswordProtectedError() from exc
        raise ParseError(
            "This file is not a valid Excel (.xlsx) workbook. "
            "Export your trial balance as .xlsx or .csv from your accounting software."
        ) from exc
    merged_row_ranges: list[str] = []

    for worksheet in workbook.worksheets:
        for merged_range in list(worksheet.merged_cells.ranges):
            min_row = merged_range.min_row
            max_row = merged_range.max_row
            min_col = merged_range.min_col
            max_col = merged_range.max_col
            top_left_value = worksheet.cell(min_row, min_col).value
            worksheet.unmerge_cells(str(merged_range))
            for row in range(min_row, max_row + 1):
                for col in range(min_col, max_col + 1):
                    worksheet.cell(row, col).value = top_left_value
            merged_row_ranges.append(f"{min_row}-{max_row}")

    if merged_row_ranges:
        logger.warning(
            "Merged cells detected in rows %s. Values inferred.",
            ", ".join(merged_row_ranges),
        )

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _parse_xlsx(content: bytes, *, functional_currency: str) -> list[TBRow]:
    excel = pd.ExcelFile(BytesIO(content), engine="openpyxl")
    sheet_names = excel.sheet_names
    if not sheet_names:
        raise ParseError("Workbook contains no worksheets.")

    first_sheet = sheet_names[0]
    first_df = pd.read_excel(
        excel, sheet_name=first_sheet, header=None, dtype=str, keep_default_na=False
    )
    first_rows = _parse_dataframe(first_df, functional_currency=functional_currency)
    if len(first_rows) >= MIN_DATA_ROWS or len(sheet_names) == 1:
        return first_rows

    second_sheet = sheet_names[1]
    logger.info(
        "First worksheet %r has fewer than %d data rows; using second worksheet %r.",
        first_sheet,
        MIN_DATA_ROWS,
        second_sheet,
    )
    second_df = pd.read_excel(
        excel, sheet_name=second_sheet, header=None, dtype=str, keep_default_na=False
    )
    return _parse_dataframe(second_df, functional_currency=functional_currency)


def _parse_dataframe(
    dataframe: pd.DataFrame,
    *,
    functional_currency: str,
) -> list[TBRow]:
    if dataframe.empty:
        return []

    working = dataframe.fillna("").astype(str)
    header_row_index = _find_header_row(working)
    if header_row_index is None:
        unrecognised = _find_unrecognised_header_row(working)
        if unrecognised is not None:
            found = _columns_found_phrase(working.iloc[unrecognised].tolist())
            raise ParseError(_missing_code_name_message(found))
        if _dataframe_looks_like_general_ledger(working):
            raise ParseError(_GL_ON_TB_MESSAGE)
        raise ParseError(_missing_code_name_message("(none)"))

    raw_headers = working.iloc[header_row_index].tolist()
    normalized = [_normalize_header(value) for value in raw_headers]
    columns_found = _columns_found_phrase(raw_headers)
    if _header_row_matches_gl_pattern(normalized):
        raise ParseError(_GL_ON_TB_MESSAGE)
    if _has_duplicate_heading(normalized):
        raise ParseError(_missing_code_name_message(columns_found))

    body = working.iloc[header_row_index + 1 :].reset_index(drop=True)
    column_names = _make_unique_columns(normalized, width=len(body.columns))
    body.columns = column_names

    try:
        column_map, tb_format = _detect_columns(
            normalized,
            column_names,
            columns_found=columns_found,
        )
    except ParseError as exc:
        if _dataframe_looks_like_general_ledger(working):
            raise ParseError(_GL_ON_TB_MESSAGE) from exc
        raise
    default_currency, per_row_currency = _detect_currency(
        body,
        column_map=column_map,
        functional_currency=functional_currency,
    )

    rows: list[TBRow] = []
    base_row = (header_row_index + 1) if header_row_index is not None else 0
    for offset, series in body.iterrows():
        spreadsheet_row_index = int(offset) + base_row + 1

        account_code = _cell_text(series, column_map["account_code"])
        account_name = _cell_text(series, column_map["account_name"])

        # Only treat as a repeated header row when the amount columns hold header
        # labels (non-numeric text like "Debit"), never when a real account *name*
        # merely contains a keyword (e.g. "Accounts Receivable", "Bank Account").
        if _is_header_row(account_code) and _amount_cells_non_numeric(
            series, column_map, tb_format
        ):
            continue

        if not account_code and not account_name:
            orphaned = _find_orphaned_amount(
                series,
                column_map,
                tb_format,
                row_index=spreadsheet_row_index,
            )
            if orphaned is None:
                continue
            column_name, amount = orphaned
            raise OrphanedAmountError(spreadsheet_row_index, amount, column_name)

        if _is_totals_row(account_name):
            continue

        if tb_format == "four_column":
            debit = parse_monetary(
                series[column_map["debit"]],
                row_index=spreadsheet_row_index,
                column_name=column_map["debit"],
            )
            credit = parse_monetary(
                series[column_map["credit"]],
                row_index=spreadsheet_row_index,
                column_name=column_map["credit"],
            )
        else:
            balance = parse_monetary(
                series[column_map["balance"]],
                row_index=spreadsheet_row_index,
                column_name=column_map["balance"],
            )
            if balance >= Decimal("0"):
                debit, credit = balance, Decimal("0")
            else:
                debit, credit = Decimal("0"), abs(balance)

        net_balance = debit - credit
        currency = (
            per_row_currency(spreadsheet_row_index, series)
            if per_row_currency is not None
            else default_currency
        )

        rows.append(
            TBRow(
                account_code=account_code,
                account_name=account_name,
                debit=debit,
                credit=credit,
                net_balance=net_balance,
                currency=currency,
                row_index=spreadsheet_row_index,
            )
        )

    return rows


def _find_header_row(dataframe: pd.DataFrame) -> int | None:
    """First row in the top of the sheet whose cells are column headings.

    Title rows such as "Trial Balance" are skipped. A match is a whole cell,
    so the word "balance" inside "balanced" does not count.
    """
    for index in range(min(10, len(dataframe))):
        normalized = [_normalize_header(value) for value in dataframe.iloc[index].tolist()]
        if _row_has_heading(normalized):
            return index
    return None


def _find_unrecognised_header_row(dataframe: pd.DataFrame) -> int | None:
    """A heading row that matches none of the known names.

    Used only so the error can list those headings. A row with a monetary
    cell is data, and its values are not reported.
    """
    for index in range(min(10, len(dataframe))):
        raw = dataframe.iloc[index].tolist()
        if _row_looks_like_unrecognised_headings(raw):
            return index
    return None


def _row_looks_like_unrecognised_headings(raw: list[object]) -> bool:
    texts: list[str] = []
    for value in raw:
        text = str(value).strip()
        if not text:
            continue
        texts.append(text)
        try:
            parse_monetary(text)
        except ParseError:
            continue
        return False
    return len(texts) >= 2


def _row_has_heading(headers: list[str]) -> bool:
    saw_amount = False
    saw_code = False
    saw_name = False
    for header in headers:
        if _heading_matches(header, _DEBIT_HEADERS | _CREDIT_HEADERS | _BALANCE_HEADERS):
            saw_amount = True
        elif _heading_matches(header, _CODE_HEADERS):
            saw_code = True
        elif _heading_matches(header, _NAME_HEADERS | _COMBINED_HEADERS):
            saw_name = True
    if saw_amount:
        return True
    return saw_code and saw_name


def _normalize_header(value: object) -> str:
    text = str(value).strip().lower()
    text = text.replace("£", " gbp ").replace("€", " eur ").replace("$", " usd ")
    text = re.sub(r"[^a-z0-9/]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _heading_key(header: str) -> str:
    """Drop a trailing currency token so "Debit GBP" is still Debit."""
    parts = header.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in _CURRENCY_HEADER_TAILS:
        return parts[0]
    return header


def _heading_matches(header: str, synonyms: frozenset[str]) -> bool:
    if not header:
        return False
    return _heading_key(header) in synonyms


def _columns_found_phrase(raw_headers: list[object]) -> str:
    """Heading text only. Data cells are not passed in."""
    labels: list[str] = []
    for value in raw_headers:
        text = str(value).strip()
        if text:
            labels.append(text)
    if not labels:
        return "(none)"
    return ", ".join(labels)


def _missing_code_name_message(columns_found: str) -> str:
    return (
        "Could not detect account code and account name columns. "
        f"Columns found: {columns_found}. "
        "Expected headings such as Account Code and Account Name."
    )


def _missing_amount_message(columns_found: str) -> str:
    return (
        "Could not detect debit and credit columns. "
        f"Columns found: {columns_found}. "
        "A single signed Balance column is not supported unless the heading is Balance. "
        "Expected headings such as Debit and Credit, or Balance."
    )


def _has_duplicate_heading(headers: list[str]) -> bool:
    seen: set[str] = set()
    for header in headers:
        if not header:
            continue
        if header in seen:
            return True
        seen.add(header)
    return False


def _make_unique_columns(headers: list[str], *, width: int) -> list[str]:
    unique: list[str] = []
    seen: dict[str, int] = {}
    for index in range(width):
        header = headers[index] if index < len(headers) else ""
        header = header or f"col_{index}"
        count = seen.get(header, 0)
        seen[header] = count + 1
        unique.append(header if count == 0 else f"{header}_{count}")
    return unique


def _header_row_matches_gl_pattern(headers: list[str]) -> bool:
    """True when a header row looks like a transaction GL, not a summarised TB.

    Each cell must be a heading. A sentence that merely contains "date" or
    "account" does not qualify.
    """
    has_date = any(_heading_matches(header, _DATE_HEADERS) for header in headers)
    has_code = any(_heading_matches(header, _CODE_HEADERS) for header in headers)
    has_name = any(
        _heading_matches(header, _NAME_HEADERS | _COMBINED_HEADERS) for header in headers
    )
    has_amounts = any(
        _heading_matches(header, _DEBIT_HEADERS | _CREDIT_HEADERS) for header in headers
    )
    return has_date and has_code and has_name and has_amounts


def _dataframe_looks_like_general_ledger(dataframe: pd.DataFrame) -> bool:
    """Scan the first rows for a Date + Account Code/Name + Debit/Credit header."""
    for index in range(min(15, len(dataframe))):
        headers = [_normalize_header(value) for value in dataframe.iloc[index].tolist()]
        if _header_row_matches_gl_pattern(headers):
            return True
    return False


def _role_indexes(headers: list[str], synonyms: frozenset[str]) -> list[int]:
    return [
        index
        for index, header in enumerate(headers)
        if _heading_matches(header, synonyms)
    ]


def _one_column(
    indexes: list[int],
    column_names: list[str],
    *,
    columns_found: str,
    amount: bool,
) -> str | None:
    if len(indexes) > 1:
        message = (
            _missing_amount_message(columns_found)
            if amount
            else _missing_code_name_message(columns_found)
        )
        raise ParseError(message)
    if not indexes:
        return None
    return column_names[indexes[0]]


def _detect_columns(
    headers: list[str],
    column_names: list[str],
    *,
    columns_found: str,
) -> tuple[dict[str, str], TBFormat]:
    """Map headings to roles. Two headings for one role is a refusal."""
    code_indexes = _role_indexes(headers, _CODE_HEADERS)
    name_indexes = _role_indexes(headers, _NAME_HEADERS)
    combined_indexes = [
        index
        for index in _role_indexes(headers, _COMBINED_HEADERS)
        if index not in code_indexes and index not in name_indexes
    ]
    account_code = _one_column(
        code_indexes, column_names, columns_found=columns_found, amount=False
    )
    account_name = _one_column(
        name_indexes, column_names, columns_found=columns_found, amount=False
    )

    if account_code is not None and account_name is None and len(combined_indexes) == 1:
        # "Code" plus "Account": Account is the name, not a second code.
        account_name = column_names[combined_indexes[0]]
    elif account_code is None and account_name is None and len(combined_indexes) == 1:
        # Xero / QuickBooks: one Account column holds the code and the name.
        account_code = column_names[combined_indexes[0]]
        account_name = account_code
    elif (
        account_code is None
        and account_name is None
        and len(combined_indexes) > 1
    ):
        raise ParseError(_missing_code_name_message(columns_found))

    if account_code is None or account_name is None:
        raise ParseError(_missing_code_name_message(columns_found))

    debit = _one_column(
        _role_indexes(headers, _DEBIT_HEADERS),
        column_names,
        columns_found=columns_found,
        amount=True,
    )
    credit = _one_column(
        _role_indexes(headers, _CREDIT_HEADERS),
        column_names,
        columns_found=columns_found,
        amount=True,
    )
    balance = _one_column(
        _role_indexes(headers, _BALANCE_HEADERS),
        column_names,
        columns_found=columns_found,
        amount=True,
    )

    if debit is not None and credit is not None:
        return {
            "account_code": account_code,
            "account_name": account_name,
            "debit": debit,
            "credit": credit,
        }, "four_column"

    if debit is not None or credit is not None:
        raise ParseError(_missing_amount_message(columns_found))

    if balance is not None:
        return {
            "account_code": account_code,
            "account_name": account_name,
            "balance": balance,
        }, "single_balance"

    raise ParseError(_missing_amount_message(columns_found))


def _detect_currency(
    dataframe: pd.DataFrame,
    *,
    column_map: dict[str, str],
    functional_currency: str,
) -> tuple[str, _PerRowCurrencyResolver | None]:
    columns = list(dataframe.columns)

    currency_column = _find_currency_column(columns)
    if currency_column is not None:
        return functional_currency, _PerRowCurrencyResolver(currency_column)

    header_currency = _currency_from_headers(columns)
    if header_currency is not None:
        return header_currency, None

    symbols = raise_if_ambiguous_currency_symbols(dataframe.to_numpy().flat)
    if len(symbols) == 1:
        return SYMBOL_TO_CURRENCY[next(iter(symbols))], None

    return functional_currency, None


def _find_currency_column(columns: list[str]) -> str | None:
    for column in columns:
        if column == "currency" or column.startswith("currency"):
            return column
    return None


def _currency_from_headers(columns: list[str]) -> str | None:
    for column in columns:
        upper = column.upper()
        for code in ISO_CURRENCIES:
            if code in upper:
                return code
    return None


def _scan_currency_symbols_from_values(values: object) -> set[str]:
    symbols: set[str] = set()
    scanned = 0
    for value in values:
        if scanned >= SCAN_CELL_LIMIT:
            break
        scanned += 1
        text = str(value)
        for symbol in SYMBOL_TO_CURRENCY:
            if symbol in text:
                symbols.add(symbol)
    return symbols


def _scan_currency_symbols(dataframe: pd.DataFrame) -> set[str]:
    return _scan_currency_symbols_from_values(dataframe.to_numpy().flat)


class _PerRowCurrencyResolver:
    def __init__(self, column_name: str) -> None:
        self._column_name = column_name

    def __call__(self, _row_index: int, series: pd.Series) -> str:
        raw = _cell_text(series, self._column_name).upper()
        if raw in ISO_CURRENCIES:
            return raw
        for symbol, code in SYMBOL_TO_CURRENCY.items():
            if symbol in raw:
                return code
        raise ParseError(f"Unsupported currency value: {raw!r}")


def _cell_text(series: pd.Series, column: str) -> str:
    value = series.get(column, "")
    return str(value).strip()


def _amount_cells_non_numeric(
    series: pd.Series, column_map: dict[str, str], tb_format: TBFormat
) -> bool:
    """True if any amount cell holds non-numeric text (a repeated header row)."""
    if tb_format == "four_column":
        cols = [column_map["debit"], column_map["credit"]]
    else:
        cols = [column_map["balance"]]
    for col in cols:
        cell = _cell_text(series, col)
        if not cell:
            continue
        try:
            parse_monetary(cell)
        except ParseError:
            return True
    return False


def _is_header_row(first_cell: str) -> bool:
    lowered = first_cell.lower()
    return any(keyword in lowered for keyword in HEADER_FIRST_CELL_KEYWORDS)


def _monetary_columns(column_map: dict[str, str], tb_format: TBFormat) -> tuple[str, ...]:
    if tb_format == "four_column":
        return (column_map["debit"], column_map["credit"])
    return (column_map["balance"],)


def _find_orphaned_amount(
    series: pd.Series,
    column_map: dict[str, str],
    tb_format: TBFormat,
    *,
    row_index: int,
) -> tuple[str, Decimal] | None:
    """Return the first nonzero monetary column for identifier-less rows, else None if blank."""
    for column_name in _monetary_columns(column_map, tb_format):
        raw_value = _cell_text(series, column_name)
        if raw_value == "":
            continue
        amount = parse_monetary(
            raw_value,
            row_index=row_index,
            column_name=column_name,
        )
        if amount != Decimal("0"):
            return column_name, amount
    return None


def _is_totals_row(account_name: str) -> bool:
    lowered = account_name.lower()
    return any(keyword in lowered for keyword in TOTALS_NAME_KEYWORDS)


def _validate_balanced(rows: list[TBRow]) -> None:
    total_debits = sum((row.debit for row in rows), Decimal("0"))
    total_credits = sum((row.credit for row in rows), Decimal("0"))
    if not decimal_eq(total_debits, total_credits):
        raise UnbalancedTrialBalanceError(total_debits, total_credits)
