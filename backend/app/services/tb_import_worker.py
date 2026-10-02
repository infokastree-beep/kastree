"""Parse a stored trial balance into an immutable version.

Called by a worker, not by the request handler. Uses Product 1's generic
importer. The four vendor-named parsers stay out of scope.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.company import Company
from app.models.confirmed_mapping import ConfirmedMapping
from app.models.source_document import SourceDocument
from app.models.tb_version import TrialBalanceLine, TrialBalanceVersion
from app.services.mapper import PriorConfirmedMapping, stored_statutory_suggestion
from app.services.parser import ParseError, UnbalancedTrialBalanceError, parse_tb_file
from app.services.source_storage import SourceObjectStorage
from app.services.spreadsheet_import import (
    SpreadsheetLimitError,
    read_csv_text,
    read_spreadsheet_text,
)
from app.services.upload_security import escape_formula_text
from findraft.engine.money import money
from findraft.engine.reconciliation import check_tb_integrity
from findraft.engine.schemas import TBLine
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd


def run_tb_import_job(
    *,
    org_id: uuid.UUID,
    version_id: uuid.UUID,
    storage: SourceObjectStorage,
) -> None:
    """Parse one pending version after the HTTP handler has committed it."""
    with SyncSessionLocal() as session:
        process_tb_version(
            session,
            org_id=org_id,
            version_id=version_id,
            storage=storage,
        )


def process_tb_version(
    session: Session,
    *,
    org_id: uuid.UUID,
    version_id: uuid.UUID,
    storage: SourceObjectStorage,
) -> TrialBalanceVersion | None:
    """Claim one pending version and parse it. Returns None if another worker holds it."""
    set_rls_org_id(session, org_id)
    claimed = session.execute(
        text(
            """
            SELECT id FROM findraft_tb_versions
            WHERE id = :id AND org_id = :org AND status = 'pending'
            FOR UPDATE SKIP LOCKED
            """
        ),
        {"id": str(version_id), "org": str(org_id)},
    ).scalar_one_or_none()
    if claimed is None:
        return None

    version = session.get(TrialBalanceVersion, version_id)
    if version is None or version.status != "pending":
        return None
    document = session.get(SourceDocument, version.source_document_id)
    company = session.get(Company, version.company_id)
    if document is None or company is None:
        version.status = "failed"
        version.error_message = "Source document was not found"
        session.commit()
        return version

    try:
        content = storage.get(key=document.storage_key)
        _enforce_sheet_caps(content, document.detected_type)
        parsed = parse_tb_file(
            content,
            filename=document.original_filename,
            functional_currency=company.functional_currency,
        )
        engine_lines: list[TBLine] = []
        stored: list[TrialBalanceLine] = []
        prior = _prior_statutory_mappings(session, version.company_id)
        for index, row in enumerate(parsed, start=1):
            debit = money(row.debit)
            credit = money(row.credit)
            if debit != row.debit or credit != row.credit:
                raise ParseError("Amount is not exact to the cent")
            name = escape_formula_text(row.account_name)
            code = escape_formula_text(row.account_code)
            if len(name) > 500 or len(code) > 64:
                raise ParseError("Account code or name is too long")
            suggested_line, confidence, method = stored_statutory_suggestion(
                code, name, prior
            )
            engine_lines.append(
                TBLine(nominal_code=code, account_name=name, debit=debit, credit=credit)
            )
            stored.append(
                TrialBalanceLine(
                    org_id=version.org_id,
                    company_id=version.company_id,
                    tb_version_id=version.id,
                    line_no=index,
                    nominal_code=code,
                    account_name=name,
                    debit=debit,
                    credit=credit,
                    suggested_canonical_line=suggested_line,
                    suggestion_confidence=confidence,
                    suggestion_method=method,
                )
            )
        integrity = check_tb_integrity(engine_lines)
        session.add_all(stored)
        if not integrity.passed:
            version.status = "failed"
            version.error_message = integrity.message
            session.commit()
            return version
        year_end = session.get(YearEnd, version.year_end_id)
        if year_end is None:
            version.status = "failed"
            version.error_message = "Year end was not found"
            session.commit()
            return version
        session.execute(
            text("SELECT id FROM findraft_year_ends WHERE id = :id FOR UPDATE"),
            {"id": str(year_end.id)},
        )
        current = session.execute(
            select(DraftVersion.version_number)
            .where(DraftVersion.year_end_id == year_end.id)
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        ).scalar_one_or_none()
        session.add(
            DraftVersion(
                org_id=year_end.org_id,
                company_id=year_end.company_id,
                year_end_id=year_end.id,
                version_number=(current or 0) + 1,
                pack_id=year_end.pack_id,
                pack_version=year_end.pack_version,
                status="draft",
                tb_version_id=version.id,
            )
        )
        version.status = "ready"
        version.error_message = None
        session.commit()
        return version
    except (
        ParseError,
        UnbalancedTrialBalanceError,
        SpreadsheetLimitError,
        ValueError,
        TypeError,
    ) as exc:
        session.rollback()
        set_rls_org_id(session, org_id)
        failed = session.get(TrialBalanceVersion, version_id)
        if failed is None:
            return None
        failed.status = "failed"
        failed.error_message = str(exc)[:500]
        session.commit()
        return failed


def _prior_statutory_mappings(
    session: Session, company_id: uuid.UUID
) -> list[PriorConfirmedMapping]:
    """Confirmed statutory lines for this company, for the prior-match tier.

    Product 1 canonical lines are not included. ``suggest_statutory_mapping``
    ignores a prior line that is not an engine line.
    """
    rows = session.execute(
        select(
            ConfirmedMapping.nominal_code,
            TrialBalanceLine.account_name,
            ConfirmedMapping.canonical_line,
        )
        .join(
            TrialBalanceLine,
            (TrialBalanceLine.tb_version_id == ConfirmedMapping.tb_version_id)
            & (TrialBalanceLine.nominal_code == ConfirmedMapping.nominal_code)
            & (TrialBalanceLine.org_id == ConfirmedMapping.org_id),
        )
        .where(ConfirmedMapping.company_id == company_id)
    ).all()
    return [
        PriorConfirmedMapping(
            source_code=code,
            source_name=name,
            canonical_line=line,
        )
        for code, name, line in rows
    ]


def _enforce_sheet_caps(content: bytes, detected_type: str) -> None:
    if detected_type == "xlsx":
        read_spreadsheet_text(content)
        return
    if detected_type == "csv":
        read_csv_text(content)
        return
    raise ParseError("Trial balance import accepts xlsx or csv files")
