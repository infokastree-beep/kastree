"""Phase 3: General Ledger → Trial Balance (deterministic, Decimal-only).

Modes (approved design — docs/gl-to-tb-design.md):
- C: YTD / full ledger in [period_start, period_end]
- A: explicit opening/bfwd rows + movements in window
- B: movements only — requires prior closing TB to enter pipeline

Golden Rule: Python does the math. No LLM. Fail closed on imbalance.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from typing import Literal, Sequence

import openpyxl
import pandas as pd

from app.services.parser import ParseError, TOLERANCE, decimal_eq, parse_monetary
from app.services.pdf_tb_extract import ExtractedTBRow, rows_to_csv_bytes

OpeningBalanceMode = Literal["A", "B", "C"]

OPENING_LABEL_RE = re.compile(
    r"\b("
    r"opening(\s+balance)?|"
    r"brought\s+forward|"
    r"b\s*/?\s*fwd|"
    r"bfwd|"
    r"balance\s+b\s*/?\s*d|"
    r"bal\.?\s*b/?d|"
    r"\bob\b"
    r")\b",
    re.IGNORECASE,
)

DATE_HEADER_KEYS = ("date", "txn date", "trans date", "transaction date", "posted")
CODE_HEADER_KEYS = ("account code", "code", "acct", "gl code", "a/c")
NAME_HEADER_KEYS = ("account name", "description", "particulars", "details")
# Avoid bare "account" / "name" — those collide with "account code".
DEBIT_HEADER_KEYS = ("debit", "dr", "debit amount")
CREDIT_HEADER_KEYS = ("credit", "cr", "credit amount")


@dataclass(frozen=True)
class GlLine:
    """One general-ledger transaction (or opening) line."""

    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal
    row_index: int
    txn_date: date | None = None
    is_opening: bool = False
    source_label: str = ""


@dataclass(frozen=True)
class PriorTbSeed:
    """Closing TB row used as opening seed for Mode B."""

    account_code: str
    account_name: str
    debit: Decimal
    credit: Decimal


@dataclass
class GlToTbResult:
    rows: list[ExtractedTBRow]
    mode: OpeningBalanceMode
    period_start: date
    period_end: date
    included_count: int
    excluded_count: int
    opening_count: int
    warnings: list[str] = field(default_factory=list)
    pipeline_eligible: bool = True
    total_debits: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")


class GlImbalanceError(Exception):
    """Hard fail — candidate TB does not balance; must not enter pipeline."""

    def __init__(
        self,
        *,
        total_debits: Decimal,
        total_credits: Decimal,
        difference: Decimal,
        top_accounts: tuple[tuple[str, str, Decimal], ...],
        included_count: int,
        excluded_count: int,
        mode: OpeningBalanceMode,
    ) -> None:
        self.total_debits = total_debits
        self.total_credits = total_credits
        self.difference = difference
        self.top_accounts = top_accounts
        self.included_count = included_count
        self.excluded_count = excluded_count
        self.mode = mode
        tops = ", ".join(
            f"{code} ({name}): {net}" for code, name, net in top_accounts[:5]
        )
        super().__init__(
            f"Converted trial balance does not balance: "
            f"debits {total_debits} ≠ credits {total_credits} "
            f"(difference {difference}). "
            f"Mode {mode}; included {included_count}, "
            f"excluded {excluded_count}. "
            f"Largest nets: {tops or 'n/a'}"
        )


class GlToTbError(Exception):
    """Fail-closed conversion / parse error (not an imbalance)."""


class ModeBRequiresPriorError(GlToTbError):
    """Mode B without a prior closing TB cannot enter the statements pipeline."""


def is_opening_label(text: str) -> bool:
    return bool(OPENING_LABEL_RE.search(text or ""))


def parse_gl_date(value: object) -> date | None:
    """Parse a cell into a calendar date, or None if blank."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    # Excel serials sometimes arrive as ints/floats
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromordinal(
                datetime(1899, 12, 30).toordinal() + int(value)
            ).date()
        except (ValueError, OverflowError):
            pass
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise GlToTbError(f"Unparseable transaction date: {text!r}")


def _norm_header(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _find_col(headers: Sequence[str], keys: Sequence[str]) -> int | None:
    """Prefer exact header matches, then substring; skip already-claimed indices via exclude."""
    for key in keys:
        for i, h in enumerate(headers):
            if h == key:
                return i
    for key in keys:
        for i, h in enumerate(headers):
            if key in h:
                return i
    return None


def _find_col_excluding(
    headers: Sequence[str],
    keys: Sequence[str],
    *,
    exclude: set[int],
) -> int | None:
    for key in keys:
        for i, h in enumerate(headers):
            if i in exclude:
                continue
            if h == key:
                return i
    for key in keys:
        for i, h in enumerate(headers):
            if i in exclude:
                continue
            if key in h:
                return i
    return None


def parse_gl_tabular(content: bytes, filename: str) -> list[GlLine]:
    """Parse Excel/CSV general ledger into GlLine rows."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig")
        # Sniff delimiter lightly
        sample = text[:2048]
        dialect = csv.excel
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            pass
        reader = csv.reader(StringIO(text), dialect)
        rows = [[c for c in row] for row in reader]
    elif lower.endswith(".xlsx"):
        wb = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
        ws = wb.active
        rows = [[cell for cell in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        raise GlToTbError("GL files must be .xlsx or .csv (or use the PDF GL path).")

    if len(rows) < 2:
        raise GlToTbError("General ledger file looks empty.")

    # Find header row in first 15 rows
    header_idx = 0
    headers: list[str] = []
    for i, row in enumerate(rows[:15]):
        cells = [_norm_header(c) for c in row]
        if _find_col(cells, CODE_HEADER_KEYS) is not None and (
            _find_col(cells, DEBIT_HEADER_KEYS) is not None
            or _find_col(cells, CREDIT_HEADER_KEYS) is not None
            or _find_col(cells, ("amount", "balance")) is not None
        ):
            header_idx = i
            headers = cells
            break
    if not headers:
        raise GlToTbError(
            "Could not detect GL columns (need account code and debit/credit)."
        )

    date_i = _find_col(headers, DATE_HEADER_KEYS)
    code_i = _find_col(headers, CODE_HEADER_KEYS)
    claimed = {i for i in (date_i, code_i) if i is not None}
    name_i = _find_col_excluding(headers, NAME_HEADER_KEYS, exclude=claimed)
    debit_i = _find_col_excluding(headers, DEBIT_HEADER_KEYS, exclude=claimed)
    credit_i = _find_col_excluding(headers, CREDIT_HEADER_KEYS, exclude=claimed)
    amount_i = _find_col_excluding(
        headers, ("amount", "net", "value"), exclude=claimed
    )

    if code_i is None:
        raise GlToTbError("Could not find an account code column.")
    if debit_i is None and credit_i is None and amount_i is None:
        raise GlToTbError("Could not find debit/credit or amount columns.")

    lines: list[GlLine] = []
    for offset, row in enumerate(rows[header_idx + 1 :], start=header_idx + 2):
        if not row or all(c is None or str(c).strip() == "" for c in row):
            continue

        def cell(idx: int | None) -> object:
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        code = str(cell(code_i) or "").strip()
        name = str(cell(name_i) or "").strip() if name_i is not None else ""
        label_blob = f"{code} {name} {cell(name_i) or ''}"
        # Skip totals rows
        if re.search(r"\b(total|totals|sum)\b", label_blob, re.I) and not code:
            continue
        if not code and not name:
            continue

        if date_i is not None and cell(date_i) not in (None, ""):
            try:
                txn_date = parse_gl_date(cell(date_i))
            except GlToTbError as exc:
                raise GlToTbError(
                    f"Row {offset}: {exc}. Fix or remove the date before converting."
                ) from exc
        else:
            txn_date = None

        debit = Decimal("0")
        credit = Decimal("0")
        try:
            if debit_i is not None or credit_i is not None:
                debit = parse_monetary(cell(debit_i), row_index=offset, column_name="debit")
                credit = parse_monetary(
                    cell(credit_i), row_index=offset, column_name="credit"
                )
            elif amount_i is not None:
                amt = parse_monetary(
                    cell(amount_i), row_index=offset, column_name="amount"
                )
                if amt >= 0:
                    debit = amt
                else:
                    credit = abs(amt)
        except ParseError as exc:
            raise GlToTbError(str(exc)) from exc

        if debit == 0 and credit == 0 and not is_opening_label(label_blob):
            # Skip empty amount rows unless opening markers
            if not code:
                continue

        opening = is_opening_label(name) or is_opening_label(label_blob)
        lines.append(
            GlLine(
                account_code=code or f"UNCODED-{offset}",
                account_name=name or code or f"Account {offset}",
                debit=debit,
                credit=credit,
                row_index=offset,
                txn_date=txn_date,
                is_opening=opening,
                source_label=name,
            )
        )

    if len(lines) < 2:
        raise GlToTbError("Need at least two general ledger lines to convert.")
    return lines


def parse_gl_pdf(content: bytes) -> list[GlLine]:
    """Extract GL-like lines from a PDF table (Date, Code, Name, Debit, Credit)."""
    import pdfplumber

    if not content.startswith(b"%PDF"):
        raise GlToTbError("This file is not a valid PDF.")

    lines: list[GlLine] = []
    with pdfplumber.open(BytesIO(content)) as pdf:
        if not pdf.pages:
            raise GlToTbError("PDF has no pages.")
        row_index = 1
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for table in tables:
                if not table:
                    continue
                headers = [_norm_header(c) for c in table[0]]
                date_i = _find_col(headers, DATE_HEADER_KEYS)
                code_i = _find_col(headers, CODE_HEADER_KEYS)
                name_i = _find_col(headers, NAME_HEADER_KEYS)
                debit_i = _find_col(headers, DEBIT_HEADER_KEYS)
                credit_i = _find_col(headers, CREDIT_HEADER_KEYS)
                if code_i is None or (debit_i is None and credit_i is None):
                    continue
                for raw in table[1:]:
                    row_index += 1
                    if not raw:
                        continue

                    def cell(idx: int | None) -> object:
                        if idx is None or idx >= len(raw):
                            return None
                        return raw[idx]

                    code = str(cell(code_i) or "").strip()
                    name = str(cell(name_i) or "").strip() if name_i is not None else ""
                    if not code and not name:
                        continue
                    if re.search(r"\b(total|totals)\b", f"{code} {name}", re.I):
                        continue
                    try:
                        txn_date = (
                            parse_gl_date(cell(date_i)) if date_i is not None else None
                        )
                    except GlToTbError as exc:
                        raise GlToTbError(str(exc)) from exc
                    try:
                        debit = parse_monetary(
                            cell(debit_i), row_index=row_index, column_name="debit"
                        )
                        credit = parse_monetary(
                            cell(credit_i), row_index=row_index, column_name="credit"
                        )
                    except ParseError as exc:
                        raise GlToTbError(str(exc)) from exc
                    opening = is_opening_label(name)
                    lines.append(
                        GlLine(
                            account_code=code or f"UNCODED-{row_index}",
                            account_name=name or code,
                            debit=debit,
                            credit=credit,
                            row_index=row_index,
                            txn_date=txn_date,
                            is_opening=opening,
                            source_label=name,
                        )
                    )
    if len(lines) < 2:
        raise GlToTbError(
            "Could not extract enough general ledger lines from this PDF. "
            "Try Excel/CSV, or ensure the PDF has a clear Date/Code/Debit/Credit table."
        )
    return lines


def _net_to_dr_cr(net: Decimal) -> tuple[Decimal, Decimal]:
    if net >= 0:
        return net, Decimal("0")
    return Decimal("0"), abs(net)


def convert_gl_to_tb(
    lines: Sequence[GlLine],
    *,
    period_start: date,
    period_end: date,
    mode: OpeningBalanceMode,
    prior_tb: Sequence[PriorTbSeed] | None = None,
) -> GlToTbResult:
    """Convert GL lines to TB rows under the approved opening-balance mode."""
    if period_start > period_end:
        raise GlToTbError("period_start must be on or before period_end.")

    warnings: list[str] = []
    excluded = 0
    opening_used = 0
    included_movements = 0

    # Per-account accumulators: net = debit - credit
    nets: dict[str, Decimal] = {}
    names: dict[str, str] = {}

    def add_net(code: str, name: str, debit: Decimal, credit: Decimal) -> None:
        nets[code] = nets.get(code, Decimal("0")) + (debit - credit)
        if name:
            names[code] = name

    if mode == "B" and not prior_tb:
        raise ModeBRequiresPriorError(
            "Mode B (period movements only) requires a prior closing trial "
            "balance to seed openings before the result can enter the "
            "statements pipeline. Switch to Mode A or C, or attach the prior TB."
        )

    if mode == "B" and prior_tb:
        for seed in prior_tb:
            add_net(seed.account_code, seed.account_name, seed.debit, seed.credit)
            opening_used += 1
        warnings.append(
            "Mode B: prior closing TB applied as openings; period movements added."
        )

    undated_blocked: list[GlLine] = []

    for line in lines:
        names.setdefault(line.account_code, line.account_name)

        if mode == "A" and line.is_opening:
            add_net(line.account_code, line.account_name, line.debit, line.credit)
            opening_used += 1
            continue

        # Movements
        if line.txn_date is None:
            # Fail closed: undated non-opening lines need attention
            if mode == "A" and line.is_opening:
                continue
            undated_blocked.append(line)
            continue

        if line.txn_date > period_end:
            excluded += 1
            continue
        if line.txn_date < period_start:
            # Never silently treat as in-period movement
            if mode == "C":
                excluded += 1
                continue
            if mode == "B":
                excluded += 1
                continue
            if mode == "A":
                # Pre-period non-opening → exclude (openings already handled)
                excluded += 1
                continue

        # In window
        add_net(line.account_code, line.account_name, line.debit, line.credit)
        included_movements += 1

    if undated_blocked:
        raise GlToTbError(
            f"{len(undated_blocked)} ledger line(s) have missing or unparseable "
            "dates. Fix the source file or remove those lines before converting."
        )

    if mode == "A" and opening_used == 0:
        warnings.append(
            "Mode A selected but no opening/brought-forward rows were detected; "
            "only period movements were included."
        )

    if mode == "C":
        warnings.append(
            "Mode C: summed all lines dated from period_start through period_end "
            "(YTD / full-ledger assumption)."
        )

    rows: list[ExtractedTBRow] = []
    total_debits = Decimal("0")
    total_credits = Decimal("0")
    account_nets: list[tuple[str, str, Decimal]] = []

    for idx, (code, net) in enumerate(
        sorted(nets.items(), key=lambda item: item[0]), start=1
    ):
        if net == 0:
            continue
        debit, credit = _net_to_dr_cr(net)
        total_debits += debit
        total_credits += credit
        account_nets.append((code, names.get(code, code), net))
        rows.append(
            ExtractedTBRow(
                account_code=code,
                account_name=names.get(code, code),
                debit=debit,
                credit=credit,
                row_index=idx,
            )
        )

    if not rows:
        raise GlToTbError(
            "No trial balance rows produced — check period dates and opening mode."
        )

    if not decimal_eq(total_debits, total_credits):
        difference = abs(total_debits - total_credits)
        top = tuple(
            sorted(account_nets, key=lambda t: abs(t[2]), reverse=True)[:8]
        )
        raise GlImbalanceError(
            total_debits=total_debits,
            total_credits=total_credits,
            difference=difference,
            top_accounts=top,
            included_count=included_movements,
            excluded_count=excluded,
            mode=mode,
        )

    return GlToTbResult(
        rows=rows,
        mode=mode,
        period_start=period_start,
        period_end=period_end,
        included_count=included_movements,
        excluded_count=excluded,
        opening_count=opening_used,
        warnings=warnings,
        pipeline_eligible=True,
        total_debits=total_debits,
        total_credits=total_credits,
    )


def convert_gl_file_to_tb(
    content: bytes,
    filename: str,
    *,
    period_start: date,
    period_end: date,
    mode: OpeningBalanceMode,
    prior_tb: Sequence[PriorTbSeed] | None = None,
) -> GlToTbResult:
    """Parse a GL file (xlsx/csv/pdf) and convert to a balanced TB."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        lines = parse_gl_pdf(content)
    else:
        lines = parse_gl_tabular(content, filename)
    return convert_gl_to_tb(
        lines,
        period_start=period_start,
        period_end=period_end,
        mode=mode,
        prior_tb=prior_tb,
    )


# Re-export for handoff symmetry with Phase 1
__all__ = [
    "GlLine",
    "GlToTbResult",
    "GlToTbError",
    "GlImbalanceError",
    "ModeBRequiresPriorError",
    "OpeningBalanceMode",
    "PriorTbSeed",
    "convert_gl_file_to_tb",
    "convert_gl_to_tb",
    "parse_gl_tabular",
    "parse_gl_pdf",
    "rows_to_csv_bytes",
    "TOLERANCE",
]
