"""Copy a built statutory document for the PDF.

The engine HTML and the JSON amounts stay as the statement builder left
them. This module decides which sections the PDF includes, and how saved
report-setup rounding, face dates, column headers, and statement type are
printed. It does not sum a trial balance.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from app.schemas.report_setup import ReportSetupWrite, pack_section_catalogue
from app.services.reconciliation import ReconciliationCheck
from app.services.report_setup import display_amount
from app.services.statutory_display import (
    _GROUPS,
    _keep,
    _nil,
    as_at_phrase,
    statement_period_phrase,
)
from app.services.statutory_statements import (
    StatementNote,
    StatementRow,
    StatutoryStatements,
    _SHORT_NOTE_TABLE_ROWS,
    _line_label,
    _signing_phrase,
    _with_note_column,
    render_statutory_html,
)
from findraft.engine.pack import load_manifest
from findraft.engine.rounding import rounding_gap
from findraft.models.year_end import YearEnd

NOT_BUILT_LINE = "[NOT BUILT: this pack does not build this statement]"

_DEFERRED = frozenset(
    {
        "cover",
        "contents",
        "directors-info",
        "directors-responsibilities",
    }
)
_UNBUILT = ("oci", "socie", "cash-flow", "trading")
_PROSE_HEADINGS = {
    "compilation": "Compilation report",
    "directors-report": "Directors' report",
}
_STATEMENTS = frozenset({"income", "sofp", "notes"})


def compose_year_end_pdf(document: StatutoryStatements, year_end: YearEnd) -> str:
    """PDF HTML for one year end. A blank report setup keeps the engine HTML."""
    return compose_pdf_html(
        document,
        report_setup=year_end.report_setup,
        period_start=year_end.period_start,
        period_end=year_end.period_end,
        first_financial_period=year_end.first_financial_period,
        approval_date=year_end.approval_date,
        signing_directors=year_end.signing_directors,
    )


def compose_pdf_html(
    document: StatutoryStatements,
    *,
    report_setup: object | None,
    period_start: date | None,
    period_end: date,
    first_financial_period: bool,
    approval_date: date | None = None,
    signing_directors: object = None,
) -> str:
    """Filter and label a copy. ``document`` and its Decimals stay put."""
    if document.html is None:
        raise ValueError("Statutory statements are not renderable")
    if report_setup is None:
        return document.html
    if not isinstance(report_setup, dict):
        raise ValueError("report setup is malformed")
    setup = _validated_setup(report_setup)
    comparative = not first_financial_period
    catalogue = pack_section_catalogue()
    saved = setup.sections
    start, end, period_note = _face_period(
        setup,
        period_start=period_start,
        period_end=period_end,
    )
    income_columns = _columns(
        setup.column_headers.ended_current,
        setup.column_headers.ended_prior,
        comparative=comparative,
        rounding=setup.rounding,
    )
    as_at_columns = _columns(
        setup.column_headers.as_at_current,
        setup.column_headers.as_at_prior,
        comparative=comparative,
        rounding=setup.rounding,
    )
    numbers = _note_numbers(document.notes)
    income_rows = _face_rows(
        document.income,
        comparative=comparative,
        rounding=setup.rounding,
        note_numbers=numbers,
    )
    sofp_rows = _face_rows(
        document.sofp,
        comparative=comparative,
        rounding=setup.rounding,
        note_numbers=numbers,
    )
    sections: list[dict[str, object]] = _front_pages(document, saved, catalogue)
    built: dict[str, dict[str, object]] = {
        "income": _statement_section(
            anchor="income",
            heading="Income statement",
            period_phrase=statement_period_phrase(start, end),
            period_note=period_note,
            compliance="",
            columns=income_columns,
            rows=income_rows,
        ),
        "sofp": _statement_section(
            anchor="sofp",
            heading="Statement of financial position",
            period_phrase=as_at_phrase(end),
            period_note=period_note,
            compliance=document.compliance_statement or "",
            columns=as_at_columns,
            rows=sofp_rows,
        ),
        "notes": {
            "kind": "notes",
            "anchor": "notes",
            "heading": "Notes",
            "period_phrase": "",
            "columns": as_at_columns,
            "notes": [
                _note_section(note, comparative=comparative, rounding=setup.rounding)
                for note in document.notes
            ],
        },
    }
    for section_id, label in _pack_order():
        if section_id in _DEFERRED or section_id in _PROSE_HEADINGS:
            continue
        if section_id in _STATEMENTS:
            sections.append(built[section_id])
            continue
        if section_id in _UNBUILT and _section_included(section_id, saved, catalogue):
            sections.append(_not_built(section_id, label))
    approved = "" if approval_date is None else approval_date.isoformat()
    return render_statutory_html(
        company_name=document.company_name,
        sections=sections,
        watermark=document.watermark,
        approval_date=approved,
        signing_directors=_signing_phrase(signing_directors),
        statement_label=_statement_label(document, setup.statement_type),
    )


def unbuilt_section_notices(year_end: YearEnd) -> tuple[ReconciliationCheck, ...]:
    """One workspace notice when a figure section this pack cannot build is on."""
    saved = _saved_flags(year_end.report_setup)
    if saved is None:
        return ()
    catalogue = pack_section_catalogue()
    labels = [
        catalogue[section_id]["label"]
        for section_id in _UNBUILT
        if _section_included(section_id, saved, catalogue)
    ]
    if not labels:
        return ()
    if len(labels) == 1:
        message = (
            f"{labels[0]} is switched on. "
            "This pack does not build this statement."
        )
    else:
        message = (
            f"{', '.join(labels)} are switched on. "
            "This pack does not build these statements."
        )
    return (
        ReconciliationCheck(
            code="V-SEC-005",
            severity="NOTICE",
            passed=False,
            message=message,
        ),
    )


def _validated_setup(raw: dict[str, object]) -> ReportSetupWrite:
    """Locked ids stay on even if a stored map says otherwise."""
    data = dict(raw)
    sections = data.get("sections")
    if isinstance(sections, dict):
        catalogue = pack_section_catalogue()
        cleaned: dict[str, bool] = {}
        for key, value in sections.items():
            if not isinstance(key, str) or not isinstance(value, bool):
                raise ValueError("report setup sections are malformed")
            if key in catalogue and catalogue[key]["lock"] == "locked":
                cleaned[key] = True
            else:
                cleaned[key] = value
        data["sections"] = cleaned
    try:
        return ReportSetupWrite.model_validate(data)
    except ValidationError as exc:
        raise ValueError("report setup is malformed") from exc


def _saved_flags(raw: object) -> dict[str, bool] | None:
    if not isinstance(raw, dict):
        return None
    sections = raw.get("sections")
    if not isinstance(sections, dict) or not sections:
        return None
    kept: dict[str, bool] = {}
    for key, value in sections.items():
        if not isinstance(key, str) or not isinstance(value, bool):
            return None
        kept[key] = value
    return kept


def _section_included(
    section_id: str,
    saved: dict[str, bool] | None,
    catalogue: dict[str, dict[str, str]],
) -> bool:
    rule = catalogue[section_id]
    if rule["lock"] == "locked":
        return True
    if saved is not None and section_id in saved:
        return saved[section_id]
    return rule["default"] == "on"


def _statement_label(document: StatutoryStatements, statement_type: str) -> str:
    """A second label beside DRAFT. It never replaces the draft watermark.

    A finalised document keeps FINAL. Compilation is not an audit or a review.
    """
    if document.watermark == "FINAL":
        return ""
    if statement_type == "compilation":
        return "Compilation"
    return ""


def _face_period(
    setup: ReportSetupWrite,
    *,
    period_start: date | None,
    period_end: date,
) -> tuple[date | None, date | None, str]:
    face_start = setup.face_dates.current_start
    face_end = setup.face_dates.current_end
    start = period_start if face_start is None else face_start
    end = period_end if face_end is None else face_end
    note = ""
    if start != period_start or end != period_end:
        trial = statement_period_phrase(period_start, period_end)
        if trial:
            note = f"Trial balance period: {trial}."
    return start, end, note


def _columns(
    current: str,
    prior: str,
    *,
    comparative: bool,
    rounding: str,
) -> list[str]:
    headings = [_column_label(current, rounding)]
    if comparative:
        headings.append(_column_label(prior, rounding))
    return headings


def _column_label(text: str, rounding: str) -> str:
    if rounding != "thousands":
        return text
    if "in thousands" in text.casefold():
        return text
    return f"{text} in thousands"


def _front_pages(
    document: StatutoryStatements,
    saved: dict[str, bool] | None,
    catalogue: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    by_heading = {heading: section_id for section_id, heading in _PROSE_HEADINGS.items()}
    pages: list[dict[str, object]] = []
    for page in document.pages:
        section_id = by_heading.get(page.heading)
        if section_id is not None and not _section_included(section_id, saved, catalogue):
            continue
        pages.append(
            {
                "kind": "prose",
                "anchor": page.heading.casefold().replace(" ", "-"),
                "heading": page.heading,
                "paragraphs": list(page.paragraphs),
            }
        )
    return pages


def _not_built(section_id: str, label: str) -> dict[str, object]:
    return {
        "kind": "prose",
        "anchor": section_id,
        "heading": label,
        "paragraphs": [NOT_BUILT_LINE],
        "page_break": True,
    }


def _statement_section(
    *,
    anchor: str,
    heading: str,
    period_phrase: str,
    period_note: str,
    compliance: str,
    columns: list[str],
    rows: list[dict[str, object]],
) -> dict[str, object]:
    section: dict[str, object] = {
        "kind": "statement",
        "anchor": anchor,
        "heading": heading,
        "period_phrase": period_phrase,
        "compliance": compliance,
        "columns": columns,
        "rows": rows,
        "show_notes": any(bool(row.get("note")) for row in rows),
    }
    if period_note:
        section["period_note"] = period_note
    return section


def _pack_order() -> tuple[tuple[str, str], ...]:
    loaded: object = load_manifest()
    if not isinstance(loaded, dict):
        raise ValueError("pack manifest is malformed")
    raw = loaded.get("sections")
    if not isinstance(raw, list):
        raise ValueError("pack sections are missing")
    ordered: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("pack section is malformed")
        section_id = item.get("id")
        label = item.get("label")
        if not isinstance(section_id, str) or not isinstance(label, str):
            raise ValueError("pack section id is malformed")
        ordered.append((section_id, label))
    return tuple(ordered)


def _note_numbers(notes: tuple[StatementNote, ...]) -> dict[str, int]:
    numbers: dict[str, int] = {}
    for note in notes:
        title = note.title or ""
        head, separator, _rest = title.partition(".")
        if separator and head.strip().isdigit():
            numbers[note.code] = int(head.strip())
    return numbers


def format_display_cell(amount: Decimal, rounding: str) -> str:
    """Comma-grouped display text. ``amount`` is not rounded in place."""
    shown = Decimal(display_amount(amount, rounding))
    text = f"{abs(shown):,}"
    if shown < 0:
        return f"({text})"
    return text


def _row_cells(
    current: Decimal,
    prior: Decimal | None,
    *,
    rounding: str,
    comparative: bool,
) -> list[str]:
    shown = [format_display_cell(current, rounding)]
    if comparative:
        shown.append("" if prior is None else format_display_cell(prior, rounding))
    return shown


def _display_difference(
    children: Sequence[Decimal | None],
    total: Decimal | None,
    rounding: str,
) -> Decimal | None:
    if total is None or any(item is None for item in children):
        return None
    amounts: list[Decimal] = [item for item in children if item is not None]
    unit = Decimal("1000") if rounding == "thousands" else Decimal("1")
    gap = rounding_gap(amounts, total, unit)
    if gap == 0:
        return None
    return -gap


def _face_rows(
    rows: tuple[StatementRow, ...],
    *,
    comparative: bool,
    rounding: str,
    note_numbers: dict[str, int],
) -> list[dict[str, object]]:
    by_label = {row.label: row for row in rows}
    printed: list[dict[str, object]] = []
    for row in rows:
        children = _GROUPS.get(row.label)
        if children is not None and _keep(row, comparative=comparative):
            if all(name in by_label for name in children):
                current_gap = _display_difference(
                    [by_label[name].current for name in children],
                    row.current,
                    rounding,
                )
                prior_gap = (
                    _display_difference(
                        [by_label[name].prior for name in children],
                        row.prior,
                        rounding,
                    )
                    if comparative
                    else None
                )
                if current_gap is not None or prior_gap is not None:
                    printed.append(
                        {
                            "label": "Rounding difference",
                            "amounts": _row_cells(
                                current_gap or Decimal("0"),
                                None if prior_gap is None else prior_gap,
                                rounding=rounding,
                                comparative=comparative,
                            ),
                        }
                    )
        if _keep(row, comparative=comparative):
            printed.append(
                {
                    "label": row.label,
                    "amounts": _row_cells(
                        row.current,
                        row.prior,
                        rounding=rounding,
                        comparative=comparative,
                    ),
                }
            )
    return _with_note_column(printed, note_numbers)


def _note_section(
    note: StatementNote,
    *,
    comparative: bool,
    rounding: str,
) -> dict[str, object]:
    if not comparative:
        visible = [line for line in note.lines if not _nil(line.current)]
    else:
        visible = [
            line
            for line in note.lines
            if not (_nil(line.current) and _nil(line.prior))
        ]
    lines: list[dict[str, object]] = [
        {
            "line": line.line,
            "label": _line_label(line.line),
            "amounts": _row_cells(
                line.current,
                line.prior,
                rounding=rounding,
                comparative=comparative,
            ),
        }
        for line in visible
    ]
    if note.lines:
        current_values = [line.current for line in note.lines]
        current_gap = _display_difference(
            current_values,
            sum(current_values, Decimal("0")),
            rounding,
        )
        prior_gap = None
        if comparative:
            prior_values = [line.prior for line in note.lines]
            prior_gap = _display_difference(
                prior_values,
                sum(prior_values, Decimal("0")),
                rounding,
            )
        if current_gap is not None or prior_gap is not None:
            lines.append(
                {
                    "line": "Rounding difference",
                    "label": "Rounding difference",
                    "amounts": _row_cells(
                        current_gap or Decimal("0"),
                        None if prior_gap is None else prior_gap,
                        rounding=rounding,
                        comparative=comparative,
                    ),
                }
            )
    fa_rows: list[dict[str, object]] = [
        {
            "asset_class": row.asset_class,
            "nbv_close": format_display_cell(row.nbv_close, rounding),
        }
        for row in note.fa_rows
    ]
    return {
        "code": note.code,
        "title": note.title or "",
        "body": note.body,
        "lines": lines,
        "lines_compact": 0 < len(lines) <= _SHORT_NOTE_TABLE_ROWS,
        "fa_rows": fa_rows,
        "fa_compact": 0 < len(fa_rows) <= _SHORT_NOTE_TABLE_ROWS,
    }
