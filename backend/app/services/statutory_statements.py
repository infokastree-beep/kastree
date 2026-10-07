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
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, Undefined
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.company import Company
from app.models.organisation import Organisation
from app.services.draft_inputs import adjusted_for_draft, latest_draft
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
_ROUNDING_LABEL = "1"

_TEXT = Environment(autoescape=False, undefined=Undefined)
_HTML = Environment(autoescape=True)


class _KeepPlaceholder(Undefined):
    """Leave an unanswered useful-life token visible. Do not invent a life."""

    def __str__(self) -> str:
        name = self._undefined_name
        return "{{" + (name if isinstance(name, str) else "") + "}}"


_POLICY_TEXT = Environment(autoescape=False, undefined=_KeepPlaceholder)

_DOCUMENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ watermark }} statutory statements</title>
<style>
  body { font-family: sans-serif; color: #111; }
  .watermark { color: #9a3412; font-weight: 700; letter-spacing: 0.12em; }
  table { border-collapse: collapse; width: 100%; margin: 0 0 1.5rem; }
  th, td { border-bottom: 1px solid #ccc; padding: 0.25rem 0.4rem; text-align: left; }
  td.amount, th.amount { text-align: right; }
  .note-body { white-space: pre-wrap; }
</style>
</head>
<body>
<p class="watermark">{{ watermark }}</p>
<h1>{{ company_name }}</h1>
{% for page in pages %}
<section>
<h2>{{ page.heading }}</h2>
{% for paragraph in page.paragraphs %}
<p>{{ paragraph }}</p>
{% endfor %}
</section>
{% endfor %}
<h2>Statement of financial position</h2>
<p>{{ compliance_statement }}</p>
<table>
<thead><tr><th>Line</th><th class="amount">Current</th><th class="amount">Prior</th></tr></thead>
<tbody>
{% for row in sofp %}
<tr><td>{{ row.label }}</td><td class="amount">{{ row.current }}</td><td class="amount">{{ row.prior }}</td></tr>
{% endfor %}
</tbody>
</table>
<h2>Income statement</h2>
<table>
<thead><tr><th>Line</th><th class="amount">Current</th><th class="amount">Prior</th></tr></thead>
<tbody>
{% for row in income %}
<tr><td>{{ row.label }}</td><td class="amount">{{ row.current }}</td><td class="amount">{{ row.prior }}</td></tr>
{% endfor %}
</tbody>
</table>
<h2>Notes</h2>
{% for note in notes %}
<section>
<h3>{{ note.code }} {% if note.title %}{{ note.title }}{% endif %}</h3>
<div class="note-body">{{ note.body }}</div>
{% if note.lines %}
<table>
<thead><tr><th>Line</th><th class="amount">Current</th><th class="amount">Prior</th></tr></thead>
<tbody>
{% for line in note.lines %}
<tr><td>{{ line.line }}</td><td class="amount">{{ line.current }}</td><td class="amount">{{ line.prior }}</td></tr>
{% endfor %}
</tbody>
</table>
{% endif %}
{% if note.fa_rows %}
<table>
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
</body>
</html>
"""


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


def _amount(value: Decimal) -> str:
    return format(value, "f")


def _director_phrase(item: dict[str, object]) -> str | None:
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    phrase = name.strip()
    appointed = item.get("appointed_on")
    resigned = item.get("resigned_on")
    notes: list[str] = []
    if isinstance(appointed, str) and appointed.strip():
        notes.append(f"appointed {appointed.strip()}")
    if isinstance(resigned, str) and resigned.strip():
        notes.append(f"resigned {resigned.strip()}")
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
            "registered_office": entity.registered_office,
            "company_number": entity.company_number,
            "directors_list": entity.directors_list,
            "currency": entity.currency,
            "rounding_unit": _ROUNDING_LABEL,
            "policy_blocks": policy_blocks,
            "avg_employees_current": entity.average_employees,
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
    aggregated: dict[str, Decimal],
    prior_canonical: dict[str, Decimal],
    fa_register: dict[str, dict[str, Decimal]] | None,
) -> tuple[tuple[StatementNote, ...], tuple[RoundingFlag, ...]]:
    notes: list[StatementNote] = []
    flags: list[RoundingFlag] = []
    for code, template in templates.items():
        if code not in selected or not isinstance(template, dict):
            continue
        prose = template.get("bodyTemplate")
        if not isinstance(prose, str):
            raise ValueError(f"note {code} has no body")
        note_context = dict(context)
        departure = template.get("departure_clause")
        if isinstance(departure, str):
            note_context["departure_clause"] = departure
        parts = [_render_prose(prose, note_context)]
        trailing = template.get("trailingText")
        if isinstance(trailing, str) and trailing:
            parts.append(_render_prose(trailing, note_context))
        for extra in ("directorLoansClause", "reservesNote"):
            clause = template.get(extra)
            if isinstance(clause, str) and clause:
                parts.append(clause)
        title = template.get("title")
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
                title=title if isinstance(title, str) else None,
                body="\n\n".join(parts),
                lines=lines,
                fa_rows=fa_rows,
            )
        )
    return tuple(notes), tuple(flags)


def _display_rows(rows: tuple[StatementRow, ...]) -> list[dict[str, str]]:
    return [
        {
            "label": row.label,
            "current": _amount(row.current),
            "prior": "" if row.prior is None else _amount(row.prior),
        }
        for row in rows
    ]


def _render_html(
    *,
    entity: StatementEntity,
    compliance: str,
    sofp: tuple[StatementRow, ...],
    income: tuple[StatementRow, ...],
    notes: tuple[StatementNote, ...],
    pages: tuple[StatutoryPage, ...],
    watermark: str,
) -> str:
    note_view = [
        {
            "code": note.code,
            "title": note.title or "",
            "body": note.body,
            "lines": [
                {
                    "line": line.line,
                    "current": _amount(line.current),
                    "prior": _amount(line.prior),
                }
                for line in note.lines
            ],
            "fa_rows": [
                {"asset_class": row.asset_class, "nbv_close": _amount(row.nbv_close)}
                for row in note.fa_rows
            ],
        }
        for note in notes
    ]
    return _HTML.from_string(_DOCUMENT).render(
        company_name=entity.name,
        compliance_statement=compliance,
        sofp=_display_rows(sofp),
        income=_display_rows(income),
        notes=note_view,
        pages=[
            {"heading": page.heading, "paragraphs": list(page.paragraphs)}
            for page in pages
        ],
        watermark=watermark,
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
    size_eligible: bool | None = None,
    approval_date: str = "",
    signing_directors: str = "",
) -> StatutoryStatements:
    directory = (
        pack_dir(pack_id, pack_version)
        if pack_id is not None and pack_version is not None
        else pack_dir()
    )
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
    notes, flags = _compose_notes(
        templates=templates,
        selected=selected,
        context=_note_context(entity, policies),
        aggregated=aggregated,
        prior_canonical=prior_canonical,
        fa_register=fa_register,
    )
    sofp_rows = _statement_rows(sofp)
    income_rows = _statement_rows(income)
    pages = build_statutory_pages(
        company_name=entity.name,
        practice_name=practice_name,
        period_end=period_end,
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
        pages=pages,
        watermark=watermark,
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
    size_eligible: bool | None = None,
    approval_date: str = "",
    signing_directors: str = "",
) -> StatutoryStatements:
    """Render a DRAFT only when every critical check has passed.

    ``prior_canonical`` uses the stored debit-positive sign. Comparatives
    are ``prior_from_mapped`` of that map, read back from the face.
    Zero lines stay on the face. Useful lives that the company has not
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
            size_eligible=size_eligible,
            approval_date=approval_date,
            signing_directors=signing_directors,
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
        size_eligible=year_end.size_eligible,
        approval_date=""
        if year_end.approval_date is None
        else year_end.approval_date.isoformat(),
        signing_directors=_signing_phrase(year_end.signing_directors),
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
        draft = await active_adopted_draft(
            session, org_id=org_id, year_end=year_end
        )
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
        size_eligible=year_end.size_eligible,
        approval_date=""
        if year_end.approval_date is None
        else year_end.approval_date.isoformat(),
        signing_directors=_signing_phrase(year_end.signing_directors),
    )
