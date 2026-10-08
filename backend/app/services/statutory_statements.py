"""Statutory SoFP, income statement, notes, and the pages in front of them.

Python owns every figure. This module calls the engine builders and the
rounding flag, then renders pack note templates. The HTML environment
autoescapes every string. The PDF fetcher refuses every URL.

The compilation report, directors' report, approval page, and audit-exemption
page are filled from the entity record and the engine profit. Missing facts
stay missing. The auditor's-report slot is not rendered. DOCX is a separate
job. A failed critical check withholds the statement. Bank reconciliation
is not called.
"""

from __future__ import annotations

import importlib.util
import json
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from jinja2 import Environment, Undefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.company import Company
from app.models.organisation import Organisation
from app.services.draft_inputs import adjusted_for_draft, latest_draft
from app.services.statutory_display import (
    as_at_phrase,
    column_headings,
    currency_name_for_policy,
    face_display_rows,
    format_iso_date,
    format_whole,
    format_whole_prose,
    note_display_lines,
    parse_iso_date,
    statement_period_phrase,
)
from app.services.statutory_pages import StatutoryPage, build_statutory_pages
from app.models.tb_version import TrialBalanceVersion
from app.services.adopted_trial_balance import (
    active_adopted_draft,
    inputs_for_adopted_draft,
)
from app.services.reconciliation import (
    ReconciliationCheck,
    ReconciliationRejected,
    ReconciliationReport,
    build_reconciliation,
    load_confirmed_inputs,
)
from findraft.engine.mapping import aggregate
from findraft.engine.money import money
from findraft.engine.notes import build_fa_grid, build_note_context, select_notes
from findraft.engine.pack import pack_dir
from findraft.engine.predicates import Unanswered, evaluate
from findraft.engine.rounding import flag_for_note
from findraft.engine.schemas import TBLine
from findraft.engine.statements import (
    build_income_statement,
    build_sofp,
    prior_from_mapped,
)
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

WATERMARK = "DRAFT"
ROUNDING_UNIT = Decimal("1")
_ROUNDING_LABEL = "whole unit"

_TEXT = Environment(autoescape=False, undefined=Undefined)
_HTML = Environment(autoescape=True)


class _KeepPlaceholder(Undefined):
    """Leave an unanswered useful-life token visible. Do not invent a life."""

    def __str__(self) -> str:
        name = self._undefined_name
        return "{{" + (name if isinstance(name, str) else "") + "}}"


_POLICY_TEXT = Environment(autoescape=False, undefined=_KeepPlaceholder)

# Sections are an ordered list. A later cover, contents page, or section
# toggle inserts or drops a block here. Amounts, dates, column headings,
# and the nil-line filter stay in statutory_display.
_DOCUMENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ page_header }} statutory statements</title>
<style>
  @page {
    size: A4;
    margin: 16mm 14mm 22mm 14mm;
    @top-left {
      content: "{{ page_header }}";
      font-family: sans-serif;
      font-size: 9pt;
      font-weight: 700;
      color: #9a3412;
    }
    @bottom-left {
      content: "The notes form part of these financial statements";
      font-family: sans-serif;
      font-size: 8pt;
      color: #333;
    }
    @bottom-right {
      content: counter(page);
      font-family: sans-serif;
      font-size: 8pt;
      color: #333;
    }
  }
  body { font-family: sans-serif; color: #111; }
  .watermark { color: #9a3412; font-weight: 700; letter-spacing: 0.12em; }
  h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
  tr, .signature { break-inside: avoid; page-break-inside: avoid; }
  .note-title, .note-intro {
    break-after: avoid;
    page-break-after: avoid;
  }
  table.note-table {
    break-inside: avoid;
    page-break-inside: avoid;
  }
  section[data-section="sofp"],
  section[data-section="income"] {
    break-before: page;
    page-break-before: always;
  }
  .statement-open {
    break-after: avoid;
    page-break-after: avoid;
    break-inside: avoid;
    page-break-inside: avoid;
  }
  table { border-collapse: collapse; width: 100%; margin: 0 0 1.5rem; }
  th, td { border-bottom: 1px solid #ccc; padding: 0.25rem 0.4rem; text-align: left; }
  td.amount, th.amount { text-align: right; font-variant-numeric: tabular-nums; }
  caption { caption-side: bottom; text-align: left; font-size: 0.9rem; padding-top: 0.35rem; }
  .note-body { white-space: pre-wrap; }
  .notes-line { font-style: italic; }
  .sign-rule { margin-top: 1.4rem; }
  a.contents-link { color: inherit; text-decoration: none; }
  a.contents-link::after { content: " " target-counter(attr(href), page); }
</style>
</head>
<body>
<p class="watermark">{{ page_header }}</p>
<h1>{{ company_name }}</h1>
{% for section in sections %}
<section data-section="{{ section.anchor }}"{% if section.page_break %} style="break-before: page; page-break-before: always;"{% endif %}>
<a id="{{ section.anchor }}"></a>
{% if section.kind == "prose" %}
<h2>{{ section.heading }}</h2>
{% for paragraph in section.paragraphs %}
<p>{{ paragraph }}</p>
{% endfor %}
{% elif section.kind == "contents" %}
<h2>{{ section.heading }}</h2>
<ul>
{% for item in section.entries %}
<li><a class="contents-link" href="#{{ item.anchor }}">{{ item.label }}</a></li>
{% endfor %}
</ul>
{% elif section.kind == "statement" %}
<div class="statement-open">
<h2>{{ section.heading }}</h2>
{% if section.period_phrase %}<p>{{ section.period_phrase }}</p>{% endif %}{% if section.period_note %}<p>{{ section.period_note }}</p>{% endif %}
{% if section.compliance %}<p>{{ section.compliance }}</p>{% endif %}
</div>
<table>
<thead><tr><th>Line</th>{% if section.show_notes %}<th>Notes</th>{% endif %}{% for column in section.columns %}<th class="amount">{{ column }}</th>{% endfor %}</tr></thead>
<tbody>
{% for row in section.rows %}
<tr><td>{{ row.label }}</td>{% if section.show_notes %}<td>{{ row.note }}</td>{% endif %}{% for amount in row.amounts %}<td class="amount">{{ amount }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
{% if section.anchor == "sofp" %}
<p class="notes-line">The notes form part of these financial statements.</p>
<section class="signature">
<p>Approved by the board and signed on its behalf by</p>
<p>{{ signature.date_line }}</p>
{% for name in signature.names %}
<p class="sign-rule">______________________________</p>
<p>{{ name }}<br>Director</p>
{% else %}
<p>A signatory has not been recorded.</p>
<p class="sign-rule">______________________________</p>
<p>Director</p>
{% endfor %}
</section>
{% endif %}
{% elif section.kind == "notes" %}
<h2>{{ section.heading }}</h2>
{% for note in section.notes %}
<section class="note-block">
<a id="note-{{ note.code }}"></a>
<h3 class="note-title">{{ note.title }}</h3>
<div class="note-body note-intro">{{ note.body }}</div>
{% if note.lines %}
<table{% if note.lines_compact %} class="note-table"{% endif %}>
<thead><tr><th>Line</th>{% for column in section.columns %}<th class="amount">{{ column }}</th>{% endfor %}</tr></thead>
<tbody>
{% for line in note.lines %}
<tr><td>{{ line.label }}</td>{% for amount in line.amounts %}<td class="amount">{{ amount }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
{% endif %}
{% if note.fa_rows %}
<table{% if note.fa_compact %} class="note-table"{% endif %}>
<thead><tr><th>Class</th><th class="amount">NBV</th></tr></thead>
<tbody>
{% for row in note.fa_rows %}
<tr><td>{{ row.asset_class }}</td><td class="amount">{{ row.nbv_close }}</td></tr>
{% endfor %}
</tbody>
</table>
{% endif %}
</section>
{% endfor %}
{% endif %}
</section>
{% endfor %}
</body>
</html>
"""


@dataclass(frozen=True)
class ShareClassFact:
    """One class stored on the company. The issued amount is not stored."""

    class_name: str
    authorised_number: int | None
    issued_number: int
    nominal_value: Decimal


@dataclass(frozen=True)
class StatementEntity:
    name: str
    registered_office: str
    company_number: str
    directors_list: str
    currency: str
    average_employees: str
    secretary: str = ""
    industry: str = ""
    principal_activity: str = ""


@dataclass(frozen=True)
class StatementRow:
    label: str
    current: Decimal
    prior: Decimal | None


@dataclass(frozen=True)
class NoteLine:
    line: str
    current: Decimal
    prior: Decimal


@dataclass(frozen=True)
class FixedAssetRow:
    asset_class: str
    opening_cost: Decimal
    additions: Decimal
    disposals: Decimal
    disposals_dep: Decimal
    closing_cost: Decimal
    opening_dep: Decimal
    charge: Decimal
    closing_dep: Decimal
    nbv_close: Decimal
    nbv_open: Decimal


@dataclass(frozen=True)
class RoundingFlag:
    statement_line_id: str
    flagged: bool
    gap: Decimal
    deeplink: str | None


@dataclass(frozen=True)
class StatementNote:
    code: str
    title: str | None
    body: str
    lines: tuple[NoteLine, ...]
    fa_rows: tuple[FixedAssetRow, ...]


@dataclass(frozen=True)
class StatutoryStatements:
    watermark: str
    renderable: bool
    blocked: bool
    build_error: str | None
    checks: tuple[ReconciliationCheck, ...]
    net_assets: Decimal | None
    profit: Decimal | None
    compliance_statement: str | None
    sofp: tuple[StatementRow, ...]
    income: tuple[StatementRow, ...]
    notes: tuple[StatementNote, ...]
    rounding_flags: tuple[RoundingFlag, ...]
    html: str | None
    pages: tuple[StatutoryPage, ...] = ()
    company_name: str = ""


class _ExternalFetchRefused(BaseException):
    """Abort PDF rendering when a URL is requested.

    WeasyPrint catches ``Exception`` from a fetcher and continues without the
    resource. A ``BaseException`` is not caught, so the statutory PDF stops
    instead of shipping with a missing external image.
    """

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


def deny_external_fetch(
    url: str,
    timeout: int = 10,
    ssl_context: object | None = None,
) -> None:
    """Refuse every URL. WeasyPrint calls this with the resource address."""
    del timeout, ssl_context
    raise ValueError(f"external fetch refused: {url}")


def _abort_on_fetch(
    url: str,
    timeout: int = 10,
    ssl_context: object | None = None,
) -> None:
    try:
        deny_external_fetch(url, timeout=timeout, ssl_context=ssl_context)
    except ValueError as exc:
        raise _ExternalFetchRefused(url) from exc


def write_statement_pdf(html: str) -> bytes:
    """Render HTML that must not pull in a remote or file resource."""
    from weasyprint import HTML  # type: ignore[import-untyped]

    try:
        document = HTML(string=html, url_fetcher=_abort_on_fetch).write_pdf()
    except _ExternalFetchRefused as exc:
        raise ValueError(f"external fetch refused: {exc.url}") from exc
    if not isinstance(document, bytes):
        raise ValueError("statement PDF was not produced")
    return document


_TITLE_NUMBER = re.compile(r"^\d+\.\s*")
_CREDITORS_CROSS_REF = "Amounts due after more than one year are analysed in Note 4."
_ABSENT_STATEMENTS = (
    "statement of changes in retained earnings",
    "statement of changes in equity",
    "statement of comprehensive income",
    "statement of cash flows",
    "cash flow statement",
)
_FALLBACK_TITLES = {
    "N0_ENTITY": "Company information",
    "N1_POLICIES": "Accounting policies",
    "N2_FA": "Fixed assets",
    "N3_DEBTORS": "Debtors",
    "N4_CREDITORS": "Creditors",
    "N5_LOANS": "Loans",
    "N6_CAPITAL": "Share capital and reserves",
    "N7_RPT": "Related party transactions",
    "N8_EMPLOYEES": "Employees",
    "N9_COMMITMENTS": "Commitments and contingencies",
}
_LINE_LABELS = {
    "TRADE_DEBTORS": "Trade debtors",
    "OTHER_DEBTORS": "Other debtors",
    "PREPAYMENTS": "Prepayments",
    "VAT_ASSET": "VAT",
    "PAYE_ASSET": "PAYE",
    "ACCRUED_INCOME": "Accrued income",
    "DEFERRED_TAX_ASSET": "Deferred tax",
    "TRADE_CREDITORS": "Trade creditors",
    "OTHER_CREDITORS": "Other creditors",
    "ACCRUALS": "Accruals",
    "CORP_TAX": "Corporation tax",
    "VAT_CREDITOR": "VAT",
    "PAYE_PRSI_CREDITOR": "PAYE/PRSI",
    "DEFERRED_INCOME": "Deferred income",
    "BANK_OVERDRAFT": "Bank overdraft",
    "LOANS_LT1Y": "Loans",
    "LEASE_LIABILITY_LT1Y": "Lease liability",
}
_FACE_NOTES = {
    "Intangible assets": "N2_FA",
    "Tangible assets": "N2_FA",
    "Fixed asset investments": "N2_FA",
    "Right-of-use assets": "N2_FA",
    "Trade debtors": "N3_DEBTORS",
    "Other debtors": "N3_DEBTORS",
    "Creditors: amounts falling due within one year": "N4_CREDITORS",
    "Lease liabilities": "N5_LOANS",
    "Creditors: amounts falling due after more than one year": "N5_LOANS",
    "Called up share capital": "N6_CAPITAL",
    "Share premium account": "N6_CAPITAL",
}
_NOT_RECORDED = {
    "registered_office": "[registered office not recorded]",
    "company_number": "[company number not recorded]",
    "directors_list": "[directors not recorded]",
    "avg_employees_current": "[average number of employees not recorded]",
    "avg_employees_prior": "[average number of employees not recorded]",
    "rpt_table": " [related party transactions not recorded]",
    "directors_agg_table": " [directors' aggregate disclosures not recorded]",
}
# While the question is unanswered the whole note is this one line. A Yes
# answer still prints the pack wording, with a placeholder for each blank
# particular. A No answer drops the note before numbering.
_UNANSWERED_NOTE = {
    "N7_RPT": "[related party transactions not recorded]",
    "N9_COMMITMENTS": "[commitments and contingencies not recorded]",
}
_PARTICULARS = {
    "capital_commitments": "[capital commitments not recorded]",
    "pension_commitments": "[retirement benefit commitments not recorded]",
    "guarantee_particulars": "[guarantees and security not recorded]",
    "charge_particulars": "[charges on assets not recorded]",
    "subsequent_events": "[subsequent events not recorded]",
}


def _human_title(code: str, raw: object) -> str:
    if isinstance(raw, str):
        stripped = _TITLE_NUMBER.sub("", raw.strip())
        if stripped:
            return stripped
    return _FALLBACK_TITLES.get(code, "Note")


def _line_label(name: str) -> str:
    labelled = _LINE_LABELS.get(name)
    if labelled is not None:
        return labelled
    return name.replace("_", " ").capitalize()


def _or_placeholder(value: str, placeholder: str) -> str:
    text = value.strip()
    return text if text else placeholder


def _names_absent_statement(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _ABSENT_STATEMENTS)


def _retarget_cross_references(body: str, numbers: dict[str, int]) -> str:
    """Point a pack cross-reference at the note that actually printed."""
    if _CREDITORS_CROSS_REF not in body:
        return body
    target = numbers.get("N4_CREDITORS")
    if target is None:
        updated = body.replace(_CREDITORS_CROSS_REF, "")
        return re.sub(r"[ \t]{2,}", " ", updated).strip()
    return body.replace(
        _CREDITORS_CROSS_REF,
        f"Amounts due after more than one year are analysed in Note {target}.",
    )


def _employees_sentence(
    context: dict[str, str], *, first_financial_period: bool
) -> str:
    """One blank reads once. A first period has no prior-year bracket."""
    current = context["avg_employees_current"]
    prior = context["avg_employees_prior"]
    lead = (
        "The average number of persons employed by the company during "
        "the reporting period was"
    )
    blank = _NOT_RECORDED["avg_employees_current"]
    if first_financial_period or (current == blank and prior == blank):
        return f"{lead} {current}."
    return f"{lead} {current} ({prior})."


_RENDERED_SECTION_IDS = ("income", "sofp", "notes")
# A note table this short stays on one page with its heading. A longer
# table may split so it does not overflow the sheet.
_SHORT_NOTE_TABLE_ROWS = 12


def _statement_order(manifest: dict[str, object]) -> tuple[str, ...]:
    """Income, balance sheet, and notes, in the order pack.json declares."""
    raw = manifest.get("sections")
    if not isinstance(raw, list):
        raise ValueError("pack sections are missing")
    order: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("pack section is malformed")
        section_id = item.get("id")
        if section_id not in _RENDERED_SECTION_IDS:
            continue
        if not isinstance(section_id, str) or section_id in order:
            raise ValueError("pack section id is malformed")
        order.append(section_id)
    if set(order) != set(_RENDERED_SECTION_IDS):
        raise ValueError(
            "pack sections do not declare the income statement, "
            "the statement of financial position, and the notes"
        )
    return tuple(order)


def _share_class_sentence(item: ShareClassFact, currency: str) -> str:
    """Issued amount is issued number times nominal value. The face figure stays."""
    issued_amount = (item.nominal_value * Decimal(item.issued_number)).quantize(
        Decimal("0.01")
    )
    authorised = (
        "not recorded"
        if item.authorised_number is None
        else f"{item.authorised_number:,}"
    )
    return (
        f"{item.class_name}: {item.issued_number:,} shares issued at "
        f"{format_whole_prose(item.nominal_value, currency)} each. "
        f"Issued amount {format_whole_prose(issued_amount, currency)}. "
        f"Authorised shares: {authorised}."
    )


def _share_capital_narrative(
    sofp: tuple[StatementRow, ...],
    *,
    currency: str,
    share_classes: tuple[ShareClassFact, ...] = (),
) -> str:
    """The amount uses the same symbolled prose form as the directors' report."""
    row = next((item for item in sofp if item.label == "Called up share capital"), None)
    shown = (
        "[called up share capital not on the face]"
        if row is None
        else format_whole_prose(row.current, currency)
    )
    face = (
        "Called up share capital presented on the statement of financial position "
        f"is {shown}."
    )
    if not share_classes:
        return f"{face} [share class analysis not recorded]"
    classes = " ".join(_share_class_sentence(item, currency) for item in share_classes)
    return f"{face} {classes}"


def _note_cell(label: str, numbers: dict[str, int]) -> str:
    code = _FACE_NOTES.get(label)
    if code is None:
        return ""
    number = numbers.get(code)
    return "" if number is None else str(number)


def _with_note_column(
    rows: list[dict[str, object]], numbers: dict[str, int]
) -> list[dict[str, object]]:
    labelled: list[dict[str, object]] = []
    for row in rows:
        label = row.get("label")
        note = _note_cell(label, numbers) if isinstance(label, str) else ""
        labelled.append({**row, "note": note})
    return labelled


def _signature_view(approval_date: str, signing_directors: str) -> dict[str, object]:
    """Names already stored on the year. A blank stays a blank line.

    The approval page and this block share format_iso_date, so an ISO value
    stored on the year end prints as 17 March 2027.
    """
    recorded = approval_date.strip()
    names = [part.strip() for part in signing_directors.split(",") if part.strip()]
    date_line = (
        f"Approved on {format_iso_date(recorded)}."
        if recorded
        else "Approval date has not been recorded."
    )
    return {"date_line": date_line, "names": names}


def _director_phrase(item: dict[str, object]) -> str | None:
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    phrase = name.strip()
    appointed = item.get("appointed_on")
    resigned = item.get("resigned_on")
    notes: list[str] = []
    if isinstance(appointed, str) and appointed.strip():
        notes.append(f"appointed {format_iso_date(appointed)}")
    if isinstance(resigned, str) and resigned.strip():
        notes.append(f"resigned {format_iso_date(resigned)}")
    if notes:
        phrase = f"{phrase} ({', '.join(notes)})"
    return phrase


def _signing_phrase(value: object) -> str:
    if not isinstance(value, list):
        return ""
    names = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return ", ".join(names)


def _directors_list(value: object) -> str:
    """Names only. A director without a name is omitted, not printed as JSON."""
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            phrase = _director_phrase(item)
            if phrase is not None:
                names.append(phrase.split(" (", 1)[0])
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return ", ".join(names)


def _directors_for_report(value: object) -> str:
    if not isinstance(value, list):
        return ""
    phrases: list[str] = []
    for item in value:
        if isinstance(item, dict):
            phrase = _director_phrase(item)
            if phrase is not None:
                phrases.append(phrase)
        elif isinstance(item, str) and item.strip():
            phrases.append(item.strip())
    return ", ".join(phrases)


def share_classes_from_company(company: Company) -> tuple[ShareClassFact, ...]:
    """Read stored classes. A row that is not a class is skipped, not invented."""
    raw = company.share_classes
    if not isinstance(raw, list):
        return ()
    facts: list[ShareClassFact] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("class_name")
        issued = item.get("issued_number")
        nominal = item.get("nominal_value")
        authorised = item.get("authorised_number")
        if not isinstance(name, str) or not name.strip():
            continue
        if isinstance(issued, bool) or not isinstance(issued, int):
            continue
        if not isinstance(nominal, str):
            continue
        if authorised is not None and (
            isinstance(authorised, bool) or not isinstance(authorised, int)
        ):
            continue
        try:
            value = Decimal(nominal)
        except InvalidOperation:
            continue
        if not value.is_finite():
            continue
        facts.append(
            ShareClassFact(
                class_name=name.strip(),
                authorised_number=authorised,
                issued_number=issued,
                nominal_value=value,
            )
        )
    return tuple(facts)


def entity_from_company(company: Company) -> StatementEntity:
    employees = company.average_employees
    return StatementEntity(
        name=company.name,
        registered_office=company.registered_office or "",
        company_number=company.company_number or "",
        directors_list=_directors_for_report(company.directors),
        currency=company.functional_currency,
        average_employees="" if employees is None else str(employees),
        secretary=company.secretary or "",
        industry=company.industry or "",
        principal_activity=company.principal_activity or "",
    )


def _draft_allowed(report: ReconciliationReport) -> bool:
    if report.blocked or report.build_error is not None:
        return False
    if report.net_assets is None or report.profit is None:
        return False
    return all(item.passed or item.severity == "WARNING" for item in report.checks)


def _withheld(
    report: ReconciliationReport,
    *,
    build_error: str | None = None,
) -> StatutoryStatements:
    error = report.build_error if build_error is None else build_error
    return StatutoryStatements(
        watermark=WATERMARK,
        renderable=False,
        blocked=report.blocked,
        build_error=error,
        checks=report.checks,
        net_assets=None,
        profit=None,
        compliance_statement=None,
        sofp=(),
        income=(),
        notes=(),
        rounding_flags=(),
        html=None,
        pages=(),
        company_name="",
    )


def _load_templates(directory: Path) -> dict[str, dict[str, object]]:
    notes_dir = directory / "notes"
    if not notes_dir.is_dir():
        raise ValueError("pack notes are missing")
    templates: dict[str, dict[str, object]] = {}
    for path in sorted(notes_dir.glob("*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"pack note is not an object: {path.name}")
        templates[path.stem] = loaded
    if not templates:
        raise ValueError("pack notes are missing")
    return templates


def _load_policies(directory: Path) -> list[dict[str, object]]:
    path = directory / "policies.py"
    if not path.is_file():
        raise ValueError("pack policies are missing")
    spec = importlib.util.spec_from_file_location("findraft_pack_policies", path)
    if spec is None or spec.loader is None:
        raise ValueError("pack policies could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    policies = getattr(module, "POLICIES", None)
    if not isinstance(policies, list):
        raise ValueError("pack policies are not a list")
    typed: list[dict[str, object]] = []
    for item in policies:
        if not isinstance(item, dict):
            raise ValueError("pack policy is not an object")
        typed.append(item)
    return typed


def _policy_blocks(policies: list[dict[str, object]], ctx: dict[str, object]) -> str:
    blocks: list[str] = []
    for policy in policies:
        policy_id = policy.get("id")
        condition = policy.get("appliesWhen")
        if not isinstance(condition, str) or not condition:
            raise ValueError(f"policy {policy_id} has no appliesWhen")
        try:
            applies = condition == "always" or bool(evaluate(condition, ctx))
        except Unanswered:
            continue
        except (ValueError, KeyError) as exc:
            raise ValueError(f"policy {policy_id} could not be evaluated") from exc
        if not applies:
            continue
        body = policy.get("body")
        if not isinstance(body, str):
            raise ValueError(f"policy {policy_id} has no body")
        rendered = _POLICY_TEXT.from_string(body).render()
        title = policy.get("title")
        heading = title.strip() if isinstance(title, str) else ""
        blocks.append(f"{heading}\n{rendered}" if heading else rendered)
    return "\n\n".join(blocks)


def _note_context(entity: StatementEntity, policy_blocks: str) -> dict[str, str]:
    blanks = (
        "departure_clause",
        "format_change_clause",
        "policy_change_clause",
        "prior_reclass_clause",
        "impairment_clause",
        "revaluation_clause",
        "capital_commitments",
        "pension_commitments",
        "guarantee_particulars",
        "charge_particulars",
        "subsequent_events",
        "share_capital_table",
        "rpt_table",
        "directors_agg_table",
        "avg_employees_prior",
    )
    context = {name: "" for name in blanks}
    context.update(
        {
            "registered_office": _or_placeholder(
                entity.registered_office, _NOT_RECORDED["registered_office"]
            ),
            "company_number": _or_placeholder(
                entity.company_number, _NOT_RECORDED["company_number"]
            ),
            "directors_list": _or_placeholder(
                entity.directors_list, _NOT_RECORDED["directors_list"]
            ),
            "currency": currency_name_for_policy(entity.currency),
            "rounding_unit": _ROUNDING_LABEL,
            "policy_blocks": policy_blocks,
            "avg_employees_current": _or_placeholder(
                entity.average_employees, _NOT_RECORDED["avg_employees_current"]
            ),
            "avg_employees_prior": _NOT_RECORDED["avg_employees_prior"],
            "rpt_table": _NOT_RECORDED["rpt_table"],
            "directors_agg_table": _NOT_RECORDED["directors_agg_table"],
        }
    )
    return context


def _render_prose(template: str, context: dict[str, str]) -> str:
    return _TEXT.from_string(template).render(context)


def _as_decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise ValueError(f"fixed-asset grid field is missing: {label}")
    return value


def _fa_rows(register: dict[str, dict[str, Decimal]]) -> tuple[FixedAssetRow, ...]:
    grid = build_fa_grid(register)
    if not isinstance(grid, list):
        raise ValueError("fixed-asset grid is missing")
    rows: list[FixedAssetRow] = []
    for item in grid:
        if not isinstance(item, dict) or "class" not in item:
            continue
        asset_class = item.get("class")
        if not isinstance(asset_class, str):
            raise ValueError("fixed-asset class is missing")
        rows.append(
            FixedAssetRow(
                asset_class=asset_class,
                opening_cost=_as_decimal(item.get("opening_cost"), "opening_cost"),
                additions=_as_decimal(item.get("additions"), "additions"),
                disposals=_as_decimal(item.get("disposals"), "disposals"),
                disposals_dep=_as_decimal(item.get("disposals_dep"), "disposals_dep"),
                closing_cost=_as_decimal(item.get("closing_cost"), "closing_cost"),
                opening_dep=_as_decimal(item.get("opening_dep"), "opening_dep"),
                charge=_as_decimal(item.get("charge"), "charge"),
                closing_dep=_as_decimal(item.get("closing_dep"), "closing_dep"),
                nbv_close=_as_decimal(item.get("nbv_close"), "nbv_close"),
                nbv_open=_as_decimal(item.get("nbv_open"), "nbv_open"),
            )
        )
    return tuple(rows)


def rounding_flag_for_lines(
    *,
    note_code: str,
    line_names: list[str],
    aggregated: dict[str, Decimal],
) -> RoundingFlag:
    """Compare rounded children with the rounded total. The engine owns the gap."""
    children = [money(aggregated.get(name, Decimal("0"))) for name in line_names]
    total = money(sum(children, Decimal("0")))
    statement_line_id = f"{note_code}.total"
    flagged = flag_for_note(children, total, ROUNDING_UNIT, statement_line_id)
    gap = flagged.get("gap")
    deeplink = flagged.get("deeplink")
    if not isinstance(gap, Decimal) or not isinstance(flagged.get("flagged"), bool):
        raise ValueError("rounding flag is missing")
    if deeplink is not None and not isinstance(deeplink, str):
        raise ValueError("rounding deeplink is missing")
    return RoundingFlag(
        statement_line_id=statement_line_id,
        flagged=bool(flagged["flagged"]),
        gap=gap,
        deeplink=deeplink,
    )


def _note_lines(
    names: list[str],
    aggregated: dict[str, Decimal],
    prior_canonical: dict[str, Decimal],
) -> tuple[NoteLine, ...]:
    lines: list[NoteLine] = []
    for name in names:
        lines.append(
            NoteLine(
                line=name,
                current=money(aggregated.get(name, Decimal("0"))),
                prior=money(prior_canonical.get(name, Decimal("0"))),
            )
        )
    return tuple(lines)


def _statement_rows(statement: dict[str, object]) -> tuple[StatementRow, ...]:
    raw = statement.get("rows")
    if not isinstance(raw, list):
        raise ValueError("statement rows are missing")
    rows: list[StatementRow] = []
    for item in raw:
        if not isinstance(item, tuple) or len(item) < 2:
            raise ValueError("statement row is malformed")
        label, current = item[0], item[1]
        prior = item[2] if len(item) > 2 else None
        if not isinstance(label, str) or not isinstance(current, Decimal):
            raise ValueError("statement row is malformed")
        if prior is not None and not isinstance(prior, Decimal):
            raise ValueError("statement comparative is malformed")
        rows.append(StatementRow(label=label, current=current, prior=prior))
    return tuple(rows)


def _note_inclusion(template: dict[str, object], ctx: dict[str, object]) -> str:
    """yes, no, or unanswered. Unanswered is never treated as no."""
    condition = template.get("includeWhen")
    if not isinstance(condition, str) or condition == "always":
        return "yes"
    try:
        affirmed = evaluate(condition, ctx)
    except Unanswered:
        return "unanswered"
    return "yes" if affirmed else "no"


def _with_particulars(context: dict[str, str]) -> dict[str, str]:
    filled = dict(context)
    for key, placeholder in _PARTICULARS.items():
        if not filled.get(key, "").strip():
            filled[key] = placeholder
    return filled


def _line_names(table: dict[str, object]) -> list[str] | None:
    names = table.get("lines_from")
    if not isinstance(names, list) or not names:
        return None
    if not all(isinstance(name, str) for name in names):
        raise ValueError("note lines_from is malformed")
    return [name for name in names if isinstance(name, str)]


def _compose_notes(
    *,
    templates: dict[str, dict[str, object]],
    selected: dict[str, object],
    context: dict[str, str],
    disclosure_ctx: dict[str, object],
    aggregated: dict[str, Decimal],
    prior_canonical: dict[str, Decimal],
    fa_register: dict[str, dict[str, Decimal]] | None,
    sofp: tuple[StatementRow, ...],
    currency: str,
    first_financial_period: bool = False,
    share_classes: tuple[ShareClassFact, ...] = (),
) -> tuple[tuple[StatementNote, ...], tuple[RoundingFlag, ...], dict[str, int]]:
    chosen = [
        code
        for code, template in templates.items()
        if code in selected
        and isinstance(template, dict)
        and not (
            code in _UNANSWERED_NOTE
            and _note_inclusion(template, disclosure_ctx) == "no"
        )
    ]
    numbers = {code: index for index, code in enumerate(chosen, start=1)}
    notes: list[StatementNote] = []
    flags: list[RoundingFlag] = []
    for code in chosen:
        template = templates[code]
        prose = template.get("bodyTemplate")
        if not isinstance(prose, str):
            raise ValueError(f"note {code} has no body")
        pending = (
            code in _UNANSWERED_NOTE
            and _note_inclusion(template, disclosure_ctx) == "unanswered"
        )
        if pending:
            notes.append(
                StatementNote(
                    code=code,
                    title=f"{numbers[code]}. {_human_title(code, template.get('title'))}",
                    body=_UNANSWERED_NOTE[code],
                    lines=(),
                    fa_rows=(),
                )
            )
            continue
        note_context = dict(context)
        if code == "N9_COMMITMENTS":
            note_context = _with_particulars(note_context)
        departure = template.get("departure_clause")
        if isinstance(departure, str):
            note_context["departure_clause"] = departure
        if code == "N6_CAPITAL":
            parts = [
                _share_capital_narrative(
                    sofp, currency=currency, share_classes=share_classes
                )
            ]
        elif code == "N8_EMPLOYEES":
            parts = [
                _employees_sentence(
                    note_context,
                    first_financial_period=first_financial_period,
                )
            ]
        else:
            parts = [_render_prose(prose, note_context)]
        trailing = template.get("trailingText")
        if isinstance(trailing, str) and trailing:
            parts.append(_render_prose(trailing, note_context))
        for extra in ("directorLoansClause", "reservesNote"):
            clause = template.get(extra)
            if (
                isinstance(clause, str)
                and clause
                and not _names_absent_statement(clause)
            ):
                parts.append(clause)
        human = _human_title(code, template.get("title"))
        lines: tuple[NoteLine, ...] = ()
        fa_rows: tuple[FixedAssetRow, ...] = ()
        table = template.get("tableSpec")
        if isinstance(table, dict):
            names = _line_names(table)
            if names is not None and table.get("totals") is True:
                lines = _note_lines(names, aggregated, prior_canonical)
                flags.append(
                    rounding_flag_for_lines(
                        note_code=code,
                        line_names=names,
                        aggregated=aggregated,
                    )
                )
            if "classes_from" in table and fa_register:
                fa_rows = _fa_rows(fa_register)
        notes.append(
            StatementNote(
                code=code,
                title=f"{numbers[code]}. {human}",
                body=_retarget_cross_references("\n\n".join(parts), numbers),
                lines=lines,
                fa_rows=fa_rows,
            )
        )
    return tuple(notes), tuple(flags), numbers


def _note_view(note: StatementNote, *, comparative: bool) -> dict[str, object]:
    """Heading, intro, and a short table are marked so the PDF keeps them together."""
    lines = [
        {**line, "label": _line_label(str(line["line"]))}
        for line in note_display_lines(note.lines, comparative=comparative)
    ]
    fa_rows = [
        {"asset_class": row.asset_class, "nbv_close": format_whole(row.nbv_close)}
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


def _render_html(
    *,
    entity: StatementEntity,
    compliance: str,
    sofp: tuple[StatementRow, ...],
    income: tuple[StatementRow, ...],
    notes: tuple[StatementNote, ...],
    note_numbers: dict[str, int],
    pages: tuple[StatutoryPage, ...],
    watermark: str,
    period_start: str = "",
    period_end: str = "",
    first_financial_period: bool = False,
    approval_date: str = "",
    signing_directors: str = "",
    statement_order: tuple[str, ...] = ("income", "sofp", "notes"),
) -> str:
    """Build the section list the template walks. The engine rows stay intact."""
    start = parse_iso_date(period_start)
    end = parse_iso_date(period_end)
    comparative = not first_financial_period
    columns = column_headings(
        period_end=end,
        currency_code=entity.currency,
        comparative=comparative,
    )
    period_phrase = statement_period_phrase(start, end)

    def _face(rows: tuple[StatementRow, ...]) -> list[dict[str, object]]:
        labelled = _with_note_column(
            face_display_rows(rows, comparative=comparative), note_numbers
        )
        return labelled

    sofp_rows = _face(sofp)
    income_rows = _face(income)
    sections: list[dict[str, object]] = [
        {
            "kind": "prose",
            "anchor": page.heading.casefold().replace(" ", "-"),
            "heading": page.heading,
            "paragraphs": list(page.paragraphs),
        }
        for page in pages
    ]
    rendered: dict[str, dict[str, object]] = {
        "sofp": {
            "kind": "statement",
            "anchor": "sofp",
            "heading": "Statement of financial position",
            "period_phrase": as_at_phrase(end),
            "compliance": compliance,
            "columns": columns,
            "rows": sofp_rows,
            "show_notes": any(bool(row.get("note")) for row in sofp_rows),
        },
        "income": {
            "kind": "statement",
            "anchor": "income",
            "heading": "Income statement",
            "period_phrase": period_phrase,
            "compliance": "",
            "columns": columns,
            "rows": income_rows,
            "show_notes": any(bool(row.get("note")) for row in income_rows),
        },
        "notes": {
            "kind": "notes",
            "anchor": "notes",
            "heading": "Notes",
            "period_phrase": "",
            "columns": columns,
            "notes": [_note_view(note, comparative=comparative) for note in notes],
        },
    }
    for anchor in statement_order:
        sections.append(rendered[anchor])
    return render_statutory_html(
        company_name=entity.name,
        sections=sections,
        watermark=watermark,
        approval_date=approval_date,
        signing_directors=signing_directors,
    )


def render_statutory_html(
    *,
    company_name: str,
    sections: list[dict[str, object]],
    watermark: str,
    approval_date: str = "",
    signing_directors: str = "",
    statement_label: str = "",
) -> str:
    """Fill the document template. Callers supply the section list.

    ``page_header`` is the watermark, with an optional second label beside
    it. A compilation draft stays ``DRAFT Compilation``. It does not become
    ``COMPILATION``.
    """
    label = statement_label.strip()
    page_header = f"{watermark} {label}" if label else watermark
    return _HTML.from_string(_DOCUMENT).render(
        company_name=company_name,
        sections=sections,
        signature=_signature_view(approval_date, signing_directors),
        watermark=watermark,
        page_header=page_header,
    )


def _render_draft(
    *,
    report: ReconciliationReport,
    tb_lines: list[TBLine],
    mappings: dict[str, str],
    prior_canonical: dict[str, Decimal],
    fa_register: dict[str, dict[str, Decimal]] | None,
    pack_id: str | None,
    pack_version: str | None,
    entity: StatementEntity,
    disclosure_flags: dict[str, bool] | None = None,
    watermark: str = WATERMARK,
    practice_name: str = "",
    period_end: str = "",
    period_start: str = "",
    first_financial_period: bool = False,
    size_eligible: bool | None = None,
    approval_date: str = "",
    signing_directors: str = "",
    share_classes: tuple[ShareClassFact, ...] = (),
) -> StatutoryStatements:
    directory = (
        pack_dir(pack_id, pack_version)
        if pack_id is not None and pack_version is not None
        else pack_dir()
    )
    manifest = json.loads((directory / "pack.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("pack manifest is malformed")
    aggregated = aggregate(tb_lines, mappings)
    validated = prior_from_mapped(prior_canonical)
    sofp = build_sofp(aggregated, validated)
    income = build_income_statement(aggregated, validated)
    sofp_profit = sofp.get("profit")
    income_profit = income.get("profit")
    if not isinstance(sofp_profit, Decimal) or sofp_profit != income_profit:
        raise ValueError(
            "income statement profit does not match the statement of financial position"
        )
    compliance = sofp.get("compliance_statement")
    if not isinstance(compliance, str) or not compliance:
        raise ValueError("compliance statement is missing")
    templates = _load_templates(directory)
    ctx = build_note_context(aggregated, templates, disclosure_flags)
    if not isinstance(ctx, dict):
        raise ValueError("note context is missing")
    selected = select_notes(templates, ctx)
    if not isinstance(selected, dict):
        raise ValueError("selected notes are missing")
    policies = _policy_blocks(_load_policies(directory), ctx)
    sofp_rows = _statement_rows(sofp)
    income_rows = _statement_rows(income)
    notes, flags, note_numbers = _compose_notes(
        templates=templates,
        selected=selected,
        context=_note_context(entity, policies),
        disclosure_ctx=ctx,
        aggregated=aggregated,
        prior_canonical=prior_canonical,
        fa_register=fa_register,
        sofp=sofp_rows,
        currency=entity.currency,
        first_financial_period=first_financial_period,
        share_classes=share_classes,
    )
    pages = build_statutory_pages(
        company_name=entity.name,
        practice_name=practice_name,
        period_end=period_end,
        period_start=period_start,
        directors=entity.directors_list,
        secretary=entity.secretary,
        principal_activity=entity.principal_activity,
        currency=entity.currency,
        profit=sofp_profit,
        size_eligible=size_eligible,
        approval_date=approval_date,
        signing_directors=signing_directors,
    )
    html = _render_html(
        entity=entity,
        compliance=compliance,
        sofp=sofp_rows,
        income=income_rows,
        notes=notes,
        note_numbers=note_numbers,
        pages=pages,
        watermark=watermark,
        period_start=period_start,
        period_end=period_end,
        first_financial_period=first_financial_period,
        approval_date=approval_date,
        signing_directors=signing_directors,
        statement_order=_statement_order(manifest),
    )
    return StatutoryStatements(
        watermark=watermark,
        renderable=True,
        blocked=False,
        build_error=None,
        checks=report.checks,
        net_assets=report.net_assets,
        profit=sofp_profit,
        compliance_statement=compliance,
        sofp=sofp_rows,
        income=income_rows,
        notes=notes,
        rounding_flags=flags,
        html=html,
        pages=pages,
        company_name=entity.name,
    )


def build_statutory_statements(
    *,
    prior_year_validated: bool,
    tb_lines: list[TBLine],
    mappings: dict[str, str],
    prior_retained_earnings: Decimal,
    prior_canonical: dict[str, Decimal] | None = None,
    fa_register: dict[str, dict[str, Decimal]] | None = None,
    pack_rules_path: Path | None = None,
    pack_id: str | None = None,
    pack_version: str | None = None,
    entity: StatementEntity | None = None,
    disclosure_flags: dict[str, bool] | None = None,
    watermark: str = WATERMARK,
    practice_name: str = "",
    period_end: str = "",
    period_start: str = "",
    first_financial_period: bool = False,
    size_eligible: bool | None = None,
    approval_date: str = "",
    signing_directors: str = "",
    share_classes: tuple[ShareClassFact, ...] = (),
) -> StatutoryStatements:
    """Render a DRAFT only when every critical check has passed.

    ``prior_canonical`` uses the stored debit-positive sign. Comparatives
    are ``prior_from_mapped`` of that map, read back from the face.
    Zero lines stay on the statement rows. The PDF omits a line that is
    nil in both presented years. Useful lives that the company has not
    supplied stay as ``{{placeholders}}``.
    """
    canonical = prior_canonical or {}
    report = build_reconciliation(
        prior_year_validated=prior_year_validated,
        tb_lines=tb_lines,
        mappings=mappings,
        prior_retained_earnings=prior_retained_earnings,
        prior_canonical=canonical,
        fa_register=fa_register,
        pack_rules_path=pack_rules_path,
    )
    if not _draft_allowed(report):
        return _withheld(report)
    if entity is None:
        return _withheld(report, build_error="company record is missing")
    try:
        return _render_draft(
            report=report,
            tb_lines=tb_lines,
            mappings=mappings,
            prior_canonical=canonical,
            fa_register=fa_register,
            pack_id=pack_id,
            pack_version=pack_version,
            entity=entity,
            disclosure_flags=disclosure_flags,
            watermark=watermark,
            practice_name=practice_name,
            period_end=period_end,
            period_start=period_start,
            first_financial_period=first_financial_period,
            size_eligible=size_eligible,
            approval_date=approval_date,
            signing_directors=signing_directors,
            share_classes=share_classes,
        )
    except (OSError, ValueError, KeyError) as exc:
        return _withheld(report, build_error=str(exc))


async def statements_for_version(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    version: TrialBalanceVersion,
    watermark: str = WATERMARK,
    use_draft: DraftVersion | None = None,
) -> StatutoryStatements:
    """Same confirmed inputs as reconciliation, plus this draft's adjustments.

    A FINAL draft is not recomputed here. The caller reads its snapshot.
    ``use_draft`` binds a specific version when it is not the latest.
    """
    if not year_end.prior_year_validated:
        return build_statutory_statements(
            prior_year_validated=False,
            tb_lines=[],
            mappings={},
            prior_retained_earnings=Decimal("0"),
            watermark=watermark,
        )
    if version.status != "ready":
        raise ReconciliationRejected("Trial balance version is not ready")
    draft: DraftVersion | None
    if use_draft is not None:
        if use_draft.org_id != org_id or use_draft.tb_version_id != version.id:
            raise ReconciliationRejected("Draft not found", 404)
        draft = use_draft
    else:
        draft = await latest_draft(session, org_id=org_id, tb_version_id=version.id)
    if draft is not None and draft.status == "final":
        raise ReconciliationRejected("FINAL output is stored on the draft", 409)
    loaded = await load_confirmed_inputs(
        session, org_id=org_id, year_end=year_end, version=version
    )
    flags: dict[str, bool] | None = None
    tb_lines = loaded.tb_lines
    mappings = loaded.mappings
    if draft is not None:
        adjusted = await adjusted_for_draft(
            session,
            org_id=org_id,
            draft=draft,
            tb_lines=loaded.tb_lines,
            mappings=loaded.mappings,
        )
        tb_lines = adjusted.tb_lines
        mappings = adjusted.mappings
        flags = adjusted.flags or None
    await aset_rls_org_id(session, org_id)
    company = await session.scalar(
        select(Company).where(
            Company.id == year_end.company_id,
            Company.org_id == org_id,
        )
    )
    if company is None or company.is_deleted:
        raise ReconciliationRejected("Company not found", 404)
    organisation = await session.scalar(
        select(Organisation).where(Organisation.id == org_id)
    )
    return build_statutory_statements(
        prior_year_validated=True,
        tb_lines=tb_lines,
        mappings=mappings,
        prior_retained_earnings=loaded.prior_retained_earnings,
        prior_canonical=loaded.prior_canonical,
        fa_register=loaded.fa_register,
        pack_rules_path=loaded.pack_rules_path,
        pack_id=year_end.pack_id,
        pack_version=year_end.pack_version,
        entity=entity_from_company(company),
        disclosure_flags=flags,
        watermark=watermark,
        practice_name="" if organisation is None else organisation.name,
        period_end=year_end.period_end.isoformat(),
        period_start=""
        if year_end.period_start is None
        else year_end.period_start.isoformat(),
        first_financial_period=year_end.first_financial_period,
        size_eligible=year_end.size_eligible,
        approval_date=""
        if year_end.approval_date is None
        else year_end.approval_date.isoformat(),
        signing_directors=_signing_phrase(year_end.signing_directors),
        share_classes=share_classes_from_company(company),
    )


async def statements_for_adopted(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    watermark: str = WATERMARK,
    use_draft: DraftVersion | None = None,
) -> StatutoryStatements:
    """Render the adopted Product 1 trial balance plus one draft's own work.

    With no draft argument, the active adopted draft supplies adjustments
    and disclosure flags. A frozen draft uses the snapshot taken when the
    next report started. A live draft re-reads Product 1 mappings.
    """
    if year_end.adopted_trial_balance_id is None:
        raise ReconciliationRejected("No confirmed trial balance is selected", 404)
    if not year_end.prior_year_validated:
        return build_statutory_statements(
            prior_year_validated=False,
            tb_lines=[],
            mappings={},
            prior_retained_earnings=Decimal("0"),
            watermark=watermark,
        )
    draft = use_draft
    if draft is None:
        draft = await active_adopted_draft(session, org_id=org_id, year_end=year_end)
    elif (
        draft.org_id != org_id
        or draft.year_end_id != year_end.id
        or draft.tb_version_id is not None
    ):
        raise ReconciliationRejected("Draft not found", 404)
    if draft is not None and draft.status == "final":
        raise ReconciliationRejected("FINAL output is stored on the draft", 409)
    loaded = await inputs_for_adopted_draft(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    flags: dict[str, bool] | None = None
    tb_lines = loaded.tb_lines
    mappings = loaded.mappings
    if draft is not None:
        adjusted = await adjusted_for_draft(
            session,
            org_id=org_id,
            draft=draft,
            tb_lines=loaded.tb_lines,
            mappings=loaded.mappings,
        )
        tb_lines = adjusted.tb_lines
        mappings = adjusted.mappings
        flags = adjusted.flags or None
    await aset_rls_org_id(session, org_id)
    company = await session.scalar(
        select(Company).where(
            Company.id == year_end.company_id,
            Company.org_id == org_id,
        )
    )
    if company is None or company.is_deleted:
        raise ReconciliationRejected("Company not found", 404)
    organisation = await session.scalar(
        select(Organisation).where(Organisation.id == org_id)
    )
    return build_statutory_statements(
        prior_year_validated=True,
        tb_lines=tb_lines,
        mappings=mappings,
        prior_retained_earnings=loaded.prior_retained_earnings,
        prior_canonical=loaded.prior_canonical,
        fa_register=loaded.fa_register,
        pack_rules_path=loaded.pack_rules_path,
        pack_id=year_end.pack_id,
        pack_version=year_end.pack_version,
        entity=entity_from_company(company),
        disclosure_flags=flags,
        watermark=watermark,
        practice_name="" if organisation is None else organisation.name,
        period_end=year_end.period_end.isoformat(),
        period_start=""
        if year_end.period_start is None
        else year_end.period_start.isoformat(),
        first_financial_period=year_end.first_financial_period,
        size_eligible=year_end.size_eligible,
        approval_date=""
        if year_end.approval_date is None
        else year_end.approval_date.isoformat(),
        signing_directors=_signing_phrase(year_end.signing_directors),
        share_classes=share_classes_from_company(company),
    )
