"""JSON shapes for statutory statements and the evidence graph."""

from __future__ import annotations

from app.services.reconciliation import ReconciliationCheck
from app.schemas.year_end import (
    EvidenceAccountOut,
    EvidenceDocumentOut,
    EvidenceLineOut,
    EvidenceResponse,
    ReconciliationCheckOut,
    RoundingFlagOut,
    StatementNoteOut,
    StatementResponse,
    StatementRowOut,
    StatutoryPageOut,
    FixedAssetGridRowOut,
    NoteLineOut,
    amount_text,
)
from app.services.statutory_evidence import EvidenceGraph
from app.services.statutory_statements import StatutoryStatements


def _checks(items: tuple[ReconciliationCheck, ...]) -> list[ReconciliationCheckOut]:
    return [
        ReconciliationCheckOut(
            code=item.code,
            severity=item.severity,
            passed=item.passed,
            message=item.message,
        )
        for item in items
    ]


def statement_response(document: StatutoryStatements) -> StatementResponse:
    return StatementResponse(
        watermark=document.watermark,
        renderable=document.renderable,
        blocked=document.blocked,
        build_error=document.build_error,
        checks=_checks(document.checks),
        net_assets=None
        if document.net_assets is None
        else amount_text(document.net_assets),
        profit=None if document.profit is None else amount_text(document.profit),
        compliance_statement=document.compliance_statement,
        sofp=[
            StatementRowOut(
                label=row.label,
                current=amount_text(row.current),
                prior=None if row.prior is None else amount_text(row.prior),
            )
            for row in document.sofp
        ],
        income=[
            StatementRowOut(
                label=row.label,
                current=amount_text(row.current),
                prior=None if row.prior is None else amount_text(row.prior),
            )
            for row in document.income
        ],
        notes=[
            StatementNoteOut(
                code=note.code,
                title=note.title,
                body=note.body,
                lines=[
                    NoteLineOut(
                        line=line.line,
                        current=amount_text(line.current),
                        prior=amount_text(line.prior),
                    )
                    for line in note.lines
                ],
                fa_rows=[
                    FixedAssetGridRowOut(
                        asset_class=row.asset_class,
                        opening_cost=amount_text(row.opening_cost),
                        additions=amount_text(row.additions),
                        disposals=amount_text(row.disposals),
                        disposals_dep=amount_text(row.disposals_dep),
                        closing_cost=amount_text(row.closing_cost),
                        opening_dep=amount_text(row.opening_dep),
                        charge=amount_text(row.charge),
                        closing_dep=amount_text(row.closing_dep),
                        nbv_close=amount_text(row.nbv_close),
                        nbv_open=amount_text(row.nbv_open),
                    )
                    for row in note.fa_rows
                ],
            )
            for note in document.notes
        ],
        rounding_flags=[
            RoundingFlagOut(
                statement_line_id=flag.statement_line_id,
                flagged=flag.flagged,
                gap=amount_text(flag.gap),
                deeplink=flag.deeplink,
            )
            for flag in document.rounding_flags
        ],
        company_name=document.company_name,
        pages=[
            StatutoryPageOut(heading=page.heading, paragraphs=list(page.paragraphs))
            for page in document.pages
        ],
    )


def evidence_response(graph: EvidenceGraph) -> EvidenceResponse:
    return EvidenceResponse(
        renderable=graph.renderable,
        blocked=graph.blocked,
        build_error=graph.build_error,
        checks=_checks(graph.checks),
        documents=[
            EvidenceDocumentOut(
                id=document.id,
                filename=document.filename,
                detected_type=document.detected_type,
                role=document.role,
                file_hash=document.file_hash,
            )
            for document in graph.documents
        ],
        lines=[
            EvidenceLineOut(
                statement=line.statement,
                label=line.label,
                amount=amount_text(line.amount),
                components=list(line.components),
                accounts=[
                    EvidenceAccountOut(
                        tb_line_id=account.tb_line_id,
                        nominal_code=account.nominal_code,
                        account_name=account.account_name,
                        mapped_line=account.mapped_line,
                        presented_line=account.presented_line,
                        balance=amount_text(account.balance),
                        contribution=amount_text(account.contribution),
                        source_document_id=account.source_document_id,
                    )
                    for account in line.accounts
                ],
            )
            for line in graph.lines
        ],
    )
