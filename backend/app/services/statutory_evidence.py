"""Statutory evidence graph: face figure to trial-balance account to document.

The engine still owns the amounts. This module reads ``aggregate().sources``
and checks that those accounts, with the statement's presentation sign,
add back to each face figure. A graph that does not tie is withheld.

The chain stops at the trial-balance source document. An adopted draft
stops at the Product 1 trial-balance accounts and that one file's hash.
Row 13 keeps journals, and any other document, outside this graph.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.source_document import SourceDocument
from app.models.tb_version import TrialBalanceLine, TrialBalanceVersion
from app.models.trial_balance import TrialBalance
from app.services.adopted_trial_balance import inputs_for_adopted_draft
from app.services.draft_inputs import adjusted_for_draft, latest_draft
from app.services.reconciliation import (
    ReconciliationCheck,
    load_confirmed_inputs,
)
from app.services.statutory_statements import (
    StatementRow,
    StatutoryStatements,
    statements_for_adopted,
    statements_for_version,
)
from findraft.engine import lines as L
from findraft.engine.mapping import aggregate
from findraft.models.draft_version import DraftVersion
from findraft.engine.money import money
from findraft.engine.schemas import TBLine
from findraft.models.year_end import YearEnd

_PROFIT = "Profit for the financial year"


@dataclass(frozen=True)
class _LineSpec:
    statement: str
    canonical_lines: frozenset[str]
    sign: int
    components: tuple[str, ...]


def _leaf(
    statement: str,
    canonical_lines: frozenset[str],
    sign: int,
) -> _LineSpec:
    return _LineSpec(
        statement=statement,
        canonical_lines=canonical_lines,
        sign=sign,
        components=(),
    )


def _total(statement: str, components: tuple[str, ...]) -> _LineSpec:
    return _LineSpec(
        statement=statement,
        canonical_lines=frozenset(),
        sign=0,
        components=components,
    )


# Labels match the engine face. Membership of each leaf is the engine group,
# so a new canonical line inside that group is picked up here. A new face
# label is refused until a spec exists, and a spec that does not add back to
# the face is withheld.
_SPECS: dict[str, _LineSpec] = {
    "Intangible assets": _leaf("sofp", L.INTANGIBLE, 1),
    "Tangible assets": _leaf("sofp", L.TANGIBLE, 1),
    "Fixed asset investments": _leaf("sofp", L.FA_INVESTMENTS, 1),
    "Right-of-use assets": _leaf("sofp", L.ROU, 1),
    "Stocks": _leaf("sofp", L.STOCKS, 1),
    "Trade debtors": _leaf("sofp", L.TRADE_DEBTORS, 1),
    "Other debtors": _leaf("sofp", L.OTHER_DEBTORS, 1),
    "Cash at bank and in hand": _leaf("sofp", L.CASH, 1),
    "Total current assets": _total(
        "sofp",
        (
            "Stocks",
            "Trade debtors",
            "Other debtors",
            "Cash at bank and in hand",
        ),
    ),
    "Creditors: amounts falling due within one year": _leaf(
        "sofp", L.CREDITORS_LT1Y, 1
    ),
    "Net current assets": _total(
        "sofp",
        (
            "Total current assets",
            "Creditors: amounts falling due within one year",
        ),
    ),
    "Total assets less current liabilities": _total(
        "sofp",
        (
            "Intangible assets",
            "Tangible assets",
            "Fixed asset investments",
            "Right-of-use assets",
            "Net current assets",
        ),
    ),
    "Lease liabilities": _leaf("sofp", L.LEASE_GT1Y, 1),
    "Creditors: amounts falling due after more than one year": _leaf(
        "sofp", L.LOANS_GT1Y, 1
    ),
    "Provisions for liabilities": _leaf("sofp", L.PROVISIONS, 1),
    "Deferred tax liability": _leaf("sofp", L.DEFERRED_TAX_LIABILITY, 1),
    "Net assets": _total(
        "sofp",
        (
            "Total assets less current liabilities",
            "Lease liabilities",
            "Creditors: amounts falling due after more than one year",
            "Provisions for liabilities",
            "Deferred tax liability",
        ),
    ),
    "Called up share capital": _leaf("sofp", L.SHARE_CAPITAL, -1),
    "Share premium account": _leaf("sofp", L.SHARE_PREMIUM, -1),
    "Profit and loss account": _LineSpec(
        statement="sofp",
        canonical_lines=L.RETAINED_EARNINGS | L.EQUITY_MOVEMENTS,
        sign=-1,
        components=(_PROFIT,),
    ),
    "Total equity": _total(
        "sofp",
        (
            "Called up share capital",
            "Share premium account",
            "Profit and loss account",
        ),
    ),
    "Turnover": _leaf("income", frozenset({"REVENUE"}), -1),
    "Cost of sales": _leaf("income", frozenset({"COST_OF_SALES"}), -1),
    "Gross profit": _total("income", ("Turnover", "Cost of sales")),
    "Distribution costs": _leaf("income", frozenset({"DISTRIBUTION_COSTS"}), -1),
    "Administrative expenses (including depreciation)": _leaf(
        "income",
        frozenset({"ADMIN_EXPENSES", "DEPRECIATION_CHARGE", "AMORTISATION_CHARGE"}),
        -1,
    ),
    "Other operating income": _leaf(
        "income", frozenset({"OTHER_OPERATING_INCOME"}), -1
    ),
    "Operating profit": _total(
        "income",
        (
            "Gross profit",
            "Distribution costs",
            "Administrative expenses (including depreciation)",
            "Other operating income",
        ),
    ),
    "Interest receivable": _leaf("income", frozenset({"INTEREST_RECEIVABLE"}), -1),
    "Interest payable": _leaf("income", frozenset({"INTEREST_PAYABLE"}), -1),
    "Profit before tax": _total(
        "income",
        ("Operating profit", "Interest receivable", "Interest payable"),
    ),
    "Tax on profit": _leaf("income", frozenset({"TAX_CHARGE"}), -1),
    _PROFIT: _total("income", ("Profit before tax", "Tax on profit")),
}


@dataclass(frozen=True)
class EvidenceAccount:
    tb_line_id: uuid.UUID | None
    nominal_code: str
    account_name: str
    mapped_line: str
    presented_line: str
    balance: Decimal
    contribution: Decimal
    source_document_id: uuid.UUID | None


@dataclass(frozen=True)
class EvidenceLine:
    statement: str
    label: str
    amount: Decimal
    accounts: tuple[EvidenceAccount, ...]
    components: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceDocument:
    id: uuid.UUID
    filename: str
    detected_type: str
    role: Literal["trial_balance"]
    file_hash: str | None = None


@dataclass(frozen=True)
class EvidenceGraph:
    renderable: bool
    blocked: bool
    build_error: str | None
    checks: tuple[ReconciliationCheck, ...]
    documents: tuple[EvidenceDocument, ...]
    lines: tuple[EvidenceLine, ...]


def _withheld(
    document: StatutoryStatements, build_error: str | None = None
) -> EvidenceGraph:
    error = document.build_error if build_error is None else build_error
    return EvidenceGraph(
        renderable=False,
        blocked=document.blocked,
        build_error=error,
        checks=document.checks,
        documents=(),
        lines=(),
    )


def _account_from_source(
    source: object,
    *,
    presented_line: str,
    sign: int,
    line_ids: dict[tuple[str, str, Decimal], list[uuid.UUID]] | None,
    source_document_id: uuid.UUID | None,
    adjustment_keys: frozenset[tuple[str, str, Decimal]] | None = None,
) -> EvidenceAccount:
    nominal = getattr(source, "nominal_code", None)
    name = getattr(source, "account_name", None)
    mapped = getattr(source, "source_line", None)
    balance = getattr(source, "balance", None)
    if (
        not isinstance(nominal, str)
        or not isinstance(name, str)
        or not isinstance(mapped, str)
        or not isinstance(balance, Decimal)
    ):
        raise ValueError("evidence source is malformed")
    stored = money(balance)
    line_id: uuid.UUID | None = None
    if line_ids is not None:
        queue = line_ids.get((nominal, name, stored))
        if queue:
            line_id = queue.pop(0)
        elif adjustment_keys is None or (nominal, name, stored) not in adjustment_keys:
            raise ValueError(f"trial-balance line missing from evidence: {nominal}")
    return EvidenceAccount(
        tb_line_id=line_id,
        nominal_code=nominal,
        account_name=name,
        mapped_line=mapped,
        presented_line=presented_line,
        balance=stored,
        contribution=money(stored * Decimal(sign)),
        source_document_id=source_document_id,
    )


def build_evidence_lines(
    *,
    tb_lines: list[TBLine],
    mappings: dict[str, str],
    sofp: tuple[StatementRow, ...],
    income: tuple[StatementRow, ...],
    line_ids: dict[tuple[str, str, Decimal], list[uuid.UUID]] | None = None,
    source_document_id: uuid.UUID | None = None,
    adjustment_keys: frozenset[tuple[str, str, Decimal]] | None = None,
) -> tuple[EvidenceLine, ...]:
    """Explain every face row from trial-balance accounts or from other rows.

    Raises ``ValueError`` when a row has no spec, a canonical balance is not
    on a face, or the accounts do not add back to the engine amount.
    """
    aggregated = aggregate(tb_lines, mappings)
    covered: set[str] = set()
    for known in _SPECS.values():
        covered |= known.canonical_lines
    missing = set(aggregated) - covered
    if missing:
        raise ValueError(
            "canonical lines missing from the evidence graph: "
            + ", ".join(sorted(missing))
        )
    sources = getattr(aggregated, "sources", None)
    if not isinstance(sources, dict):
        raise ValueError("evidence sources are missing")
    face = {row.label: row.current for row in (*sofp, *income)}
    lines: list[EvidenceLine] = []
    for row in (*sofp, *income):
        spec = _SPECS.get(row.label)
        if spec is None:
            raise ValueError(f"statement row has no evidence spec: {row.label}")
        accounts: list[EvidenceAccount] = []
        raw = Decimal("0")
        for canonical in sorted(spec.canonical_lines):
            posted = sources.get(canonical, [])
            if not isinstance(posted, list):
                raise ValueError(f"evidence sources are malformed: {canonical}")
            for source in posted:
                account = _account_from_source(
                    source,
                    presented_line=canonical,
                    sign=spec.sign,
                    line_ids=line_ids,
                    source_document_id=source_document_id,
                    adjustment_keys=adjustment_keys,
                )
                accounts.append(account)
                raw += account.balance
        signed = money(raw * Decimal(spec.sign)) if spec.sign else Decimal("0")
        component_total = Decimal("0")
        for label in spec.components:
            amount = face.get(label)
            if amount is None:
                raise ValueError(f"evidence component is missing: {label}")
            component_total += amount
        tied = money(signed + component_total)
        if tied != row.current:
            raise ValueError(f"evidence does not tie: {row.label}")
        lines.append(
            EvidenceLine(
                statement=spec.statement,
                label=row.label,
                amount=row.current,
                accounts=tuple(accounts),
                components=spec.components,
            )
        )
    return tuple(lines)


def _line_queues(
    rows: list[TrialBalanceLine],
) -> dict[tuple[str, str, Decimal], list[uuid.UUID]]:
    queues: dict[tuple[str, str, Decimal], list[uuid.UUID]] = {}
    for row in rows:
        key = (row.nominal_code, row.account_name, money(row.debit - row.credit))
        queues.setdefault(key, []).append(row.id)
    return queues


async def _document(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
) -> EvidenceDocument:
    await aset_rls_org_id(session, org_id)
    document = await session.scalar(
        select(SourceDocument).where(
            SourceDocument.id == document_id,
            SourceDocument.org_id == org_id,
        )
    )
    if document is None:
        raise ValueError("trial balance source document is missing")
    return EvidenceDocument(
        id=document.id,
        filename=document.original_filename,
        detected_type=document.detected_type,
        role="trial_balance",
    )


async def evidence_for_version(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    version: TrialBalanceVersion,
    use_draft: DraftVersion | None = None,
) -> EvidenceGraph:
    """Same render gate as the statutory draft. The graph is computed live."""
    document = await statements_for_version(
        session,
        org_id=org_id,
        year_end=year_end,
        version=version,
        use_draft=use_draft,
    )
    if not document.renderable:
        return _withheld(document)
    loaded = await load_confirmed_inputs(
        session, org_id=org_id, year_end=year_end, version=version
    )
    draft = (
        use_draft
        if use_draft is not None
        else await latest_draft(session, org_id=org_id, tb_version_id=version.id)
    )
    adjustment_keys: frozenset[tuple[str, str, Decimal]] = frozenset()
    tb_lines = loaded.tb_lines
    mappings = loaded.mappings
    if draft is not None and draft.status != "final":
        adjusted = await adjusted_for_draft(
            session,
            org_id=org_id,
            draft=draft,
            tb_lines=loaded.tb_lines,
            mappings=loaded.mappings,
        )
        tb_lines = adjusted.tb_lines
        mappings = adjusted.mappings
        adjustment_keys = adjusted.adjustment_keys
    await aset_rls_org_id(session, org_id)
    tb_rows = list(
        (
            await session.scalars(
                select(TrialBalanceLine)
                .where(
                    TrialBalanceLine.tb_version_id == version.id,
                    TrialBalanceLine.org_id == org_id,
                )
                .order_by(TrialBalanceLine.line_no)
            )
        ).all()
    )
    try:
        trial_balance = await _document(
            session,
            org_id=org_id,
            document_id=version.source_document_id,
        )
        lines = build_evidence_lines(
            tb_lines=tb_lines,
            mappings=mappings,
            sofp=document.sofp,
            income=document.income,
            line_ids=_line_queues(tb_rows),
            source_document_id=trial_balance.id,
            adjustment_keys=adjustment_keys,
        )
    except (OSError, ValueError) as exc:
        return _withheld(document, str(exc))
    return EvidenceGraph(
        renderable=True,
        blocked=False,
        build_error=None,
        checks=document.checks,
        documents=(trial_balance,),
        lines=lines,
    )


async def evidence_for_adopted(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    use_draft: DraftVersion | None = None,
) -> EvidenceGraph:
    """Face figures tied to Product 1 accounts. The file is named by its hash."""
    document = await statements_for_adopted(
        session,
        org_id=org_id,
        year_end=year_end,
        use_draft=use_draft,
    )
    if not document.renderable:
        return _withheld(document)
    if year_end.adopted_trial_balance_id is None:
        return _withheld(document, "No confirmed trial balance is selected")
    draft = use_draft
    if draft is None:
        from app.services.adopted_trial_balance import active_adopted_draft

        draft = await active_adopted_draft(session, org_id=org_id, year_end=year_end)
    loaded = await inputs_for_adopted_draft(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    adjustment_keys: frozenset[tuple[str, str, Decimal]] = frozenset()
    tb_lines = loaded.tb_lines
    mappings = loaded.mappings
    if draft is not None and draft.status != "final":
        adjusted = await adjusted_for_draft(
            session,
            org_id=org_id,
            draft=draft,
            tb_lines=loaded.tb_lines,
            mappings=loaded.mappings,
        )
        tb_lines = adjusted.tb_lines
        mappings = adjusted.mappings
        adjustment_keys = adjusted.adjustment_keys
    await aset_rls_org_id(session, org_id)
    trial_balance = await session.get(TrialBalance, year_end.adopted_trial_balance_id)
    if (
        trial_balance is None
        or trial_balance.company_id != year_end.company_id
        or trial_balance.is_deleted
    ):
        return _withheld(document, "trial balance file is missing")
    file_hash = trial_balance.file_hash or ""
    source = EvidenceDocument(
        id=trial_balance.id,
        filename=file_hash,
        detected_type=trial_balance.file_type,
        role="trial_balance",
        file_hash=file_hash or None,
    )
    try:
        lines = build_evidence_lines(
            tb_lines=tb_lines,
            mappings=mappings,
            sofp=document.sofp,
            income=document.income,
            line_ids=None,
            source_document_id=None,
            adjustment_keys=adjustment_keys,
        )
    except ValueError as exc:
        return _withheld(document, str(exc))
    return EvidenceGraph(
        renderable=True,
        blocked=False,
        build_error=None,
        checks=document.checks,
        documents=(source,),
        lines=lines,
    )
