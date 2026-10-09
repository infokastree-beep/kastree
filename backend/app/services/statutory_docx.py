"""Build a statutory DOCX from a JSON-ready statement payload.

Every string written into the document is escaped when it begins with a
formula-leading character. The builder does not calculate figures.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

_FORMULA_LEAD = ("=", "+", "-", "@")


def escape_export_text(value: str) -> str:
    """Prefix formula-leading text so a later spreadsheet open does not run it."""
    if value.startswith(_FORMULA_LEAD):
        return "'" + value
    return value


def build_docx(payload: Mapping[str, object], dest: Path) -> None:
    """Write one DOCX. Imported after the child applies its memory cap."""
    from docx import Document

    document = Document()
    document.add_paragraph(escape_export_text(_required_text(payload, "watermark")))
    document.add_heading(
        escape_export_text(_required_text(payload, "company_name")), level=1
    )
    composed = payload.get("composed")
    if isinstance(composed, list):
        _write_composed(document, composed)
        document.save(str(dest))
        return
    for page in _mappings(payload.get("pages"), "pages"):
        _start_new_page(document, page.get("new_page"))
        document.add_heading(
            escape_export_text(_required_text(page, "heading")), level=2
        )
        for paragraph in _strings(page.get("paragraphs"), "paragraphs"):
            document.add_paragraph(escape_export_text(paragraph))
    _start_new_page(document, payload.get("sofp_new_page"))
    document.add_heading("Statement of financial position", level=2)
    compliance = payload.get("compliance_statement")
    if isinstance(compliance, str) and compliance:
        document.add_paragraph(escape_export_text(compliance))
    _amount_table(document, _mappings(payload.get("sofp"), "sofp"))
    _start_new_page(document, payload.get("income_new_page"))
    document.add_heading("Income statement", level=2)
    _amount_table(document, _mappings(payload.get("income"), "income"))
    _start_new_page(document, payload.get("notes_new_page"))
    document.add_heading("Notes", level=2)
    for note in _mappings(payload.get("notes"), "notes"):
        title = _required_text(note, "title")
        code = _required_text(note, "code")
        heading = code if not title else f"{code} {title}"
        document.add_heading(escape_export_text(heading), level=3)
        document.add_paragraph(escape_export_text(_required_text(note, "body")))
        lines = note.get("lines")
        if lines:
            _amount_table(document, _mappings(lines, "lines"), label_key="line")
    document.save(str(dest))


def _start_new_page(document: object, enabled: object) -> None:
    """A true flag inserts a page break. A missing flag keeps the old flow."""
    if enabled is not True:
        return
    add_page_break = getattr(document, "add_page_break", None)
    if not callable(add_page_break):
        raise TypeError("document is missing")
    add_page_break()


def _write_composed(document: object, sections: Sequence[object]) -> None:
    add_heading = getattr(document, "add_heading", None)
    add_paragraph = getattr(document, "add_paragraph", None)
    if not callable(add_heading) or not callable(add_paragraph):
        raise TypeError("document is missing")
    for section in sections:
        if not isinstance(section, Mapping):
            raise ValueError("composed section is missing")
        _start_new_page(document, section.get("page_break") is True)
        add_heading(escape_export_text(_required_text(section, "heading")), level=2)
        kind = section.get("kind")
        if kind == "contents":
            for entry in _mappings(section.get("entries"), "entries"):
                add_paragraph(escape_export_text(_required_text(entry, "label")))
            continue
        if kind == "statement":
            phrase = section.get("period_phrase")
            if isinstance(phrase, str) and phrase:
                add_paragraph(escape_export_text(phrase))
            note = section.get("period_note")
            if isinstance(note, str) and note:
                add_paragraph(escape_export_text(note))
            compliance = section.get("compliance")
            if isinstance(compliance, str) and compliance:
                add_paragraph(escape_export_text(compliance))
            _composed_table(
                document,
                _strings(section.get("columns"), "columns"),
                _mappings(section.get("rows"), "rows"),
            )
            continue
        if kind == "notes":
            for note in _mappings(section.get("notes"), "notes"):
                title = _required_text(note, "title")
                code = _required_text(note, "code")
                heading = code if not title else f"{code} {title}"
                add_heading(escape_export_text(heading), level=3)
                add_paragraph(escape_export_text(_required_text(note, "body")))
                _composed_table(
                    document,
                    _strings(section.get("columns"), "columns"),
                    _mappings(note.get("lines"), "lines"),
                    label_key="label",
                )
            continue
        for paragraph in _strings(section.get("paragraphs"), "paragraphs"):
            add_paragraph(escape_export_text(paragraph))


def _composed_table(
    document: object,
    columns: Sequence[str],
    rows: Sequence[Mapping[str, object]],
    *,
    label_key: str = "label",
) -> None:
    add_table = getattr(document, "add_table", None)
    if not callable(add_table):
        raise TypeError("document is missing")
    width = 1 + len(columns)
    table = add_table(rows=1 + len(rows), cols=width)
    headers = table.rows[0].cells
    headers[0].text = "Line"
    for index, column in enumerate(columns, start=1):
        headers[index].text = escape_export_text(column)
    for index, row in enumerate(rows, start=1):
        cells = table.rows[index].cells
        cells[0].text = escape_export_text(_required_text(row, label_key))
        amounts = row.get("amounts")
        if not isinstance(amounts, list):
            raise ValueError("composed amounts are missing")
        for column_index, amount in enumerate(amounts, start=1):
            if not isinstance(amount, str):
                raise ValueError("composed amount is missing")
            if column_index < width:
                cells[column_index].text = escape_export_text(amount)


def _amount_table(
    document: object,
    rows: Sequence[Mapping[str, object]],
    *,
    label_key: str = "label",
) -> None:
    add_table = getattr(document, "add_table", None)
    if not callable(add_table):
        raise TypeError("document is missing")
    table = add_table(rows=1 + len(rows), cols=3)
    headers = table.rows[0].cells
    headers[0].text = "Line"
    headers[1].text = "Current"
    headers[2].text = "Prior"
    for index, row in enumerate(rows, start=1):
        cells = table.rows[index].cells
        cells[0].text = escape_export_text(_required_text(row, label_key))
        cells[1].text = escape_export_text(_required_text(row, "current"))
        cells[2].text = escape_export_text(_required_text(row, "prior"))


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is missing")
    return value


def _mappings(value: object, key: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError(f"{key} is missing")
    rows: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{key} is missing")
        rows.append(item)
    return tuple(rows)


def _strings(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{key} is missing")
    texts: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} is missing")
        texts.append(item)
    return tuple(texts)
