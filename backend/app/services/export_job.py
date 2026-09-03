"""Background export job — loads package + org tier from DB, never from the request."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.client import Client
from app.models.company import Company
from app.models.export import Export
from app.models.financial_statement import FinancialStatement
from app.models.organisation import Organisation
from app.models.risk_flag import RiskFlag
from app.models.statement_line_item import StatementLineItem
from app.models.trial_balance import TrialBalance
from app.models.variance_analysis import VarianceAnalysis
from app.schemas.risk import AffectedAccount, RiskFlagRecord
from app.schemas.variance import VarianceAnalysisResult
from app.services.exporter import (
    ExportBranding,
    ExportPackage,
    ObjectStorage,
    S3ObjectStorage,
    run_export_job,
)
from app.services.mapper import MappingResult
from app.services.statements import StatementLineItemRecord

logger = logging.getLogger(__name__)


def default_object_storage() -> ObjectStorage:
    return S3ObjectStorage()


def run_export_job_task(
    *,
    export_id: uuid.UUID,
    org_id: uuid.UUID,
    storage: ObjectStorage | None = None,
) -> None:
    """BackgroundTasks entrypoint: rebuild package from DB and run exporter."""
    object_storage = storage if storage is not None else default_object_storage()
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        export = session.get(Export, export_id)
        if export is None:
            logger.error("Export %s not found for background job", export_id)
            return
        try:
            branding, package, organisation = _load_export_context(
                session, export=export, org_id=org_id
            )
            run_export_job(
                export,
                format=export.format,  # type: ignore[arg-type]
                branding=branding,
                package=package,
                organisation=organisation,
                storage=object_storage,
                export_id=export.id,
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("Export background job failed for %s", export_id)
            # Produce an operator-readable error message. NoCredentialsError means
            # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY are not set in Railway.
            error_type = type(exc).__name__
            if error_type in {"NoCredentialsError", "CredentialRetrievalError"}:
                user_msg = (
                    "Object storage credentials are not configured. "
                    "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (or R2 equivalents) "
                    "in the Railway environment."
                )
            else:
                user_msg = f"Export job failed: {exc}" if str(exc) else "Export job failed unexpectedly"
            with SyncSessionLocal() as err_session:
                set_rls_org_id(err_session, org_id)
                failed = err_session.get(Export, export_id)
                if failed is not None:
                    failed.status = "failed"
                    failed.error_message = user_msg
                    err_session.commit()


def _load_export_context(
    session: Session,
    *,
    export: Export,
    org_id: uuid.UUID,
) -> tuple[ExportBranding, ExportPackage, Organisation]:
    """Resolve TB → client → organisation (DB tier) and statement package.

    Watermarking uses ``organisation.subscription_tier`` from this DB read only.
    """
    tb = session.get(TrialBalance, export.tb_id)
    if tb is None:
        raise ValueError("Trial balance not found for export")

    company = session.get(Company, tb.company_id)
    if company is None or company.is_deleted:
        raise ValueError("Company not found for export")

    client = session.get(Client, company.client_id)
    if client is None or client.org_id != org_id or client.is_deleted:
        raise ValueError("Client not found for export")

    # Authoritative tier — organisations row via client.org_id, never request body.
    organisation = session.get(Organisation, client.org_id)
    if organisation is None or organisation.id != org_id:
        raise ValueError("Organisation not found for export")

    options = export.options or {}
    include_mapping = bool(options.get("include_mapping_summary", True))
    include_risk = bool(options.get("include_risk_report", True))

    sopl = _load_statement_lines(session, tb.id, "SOPL")
    sofp = _load_statement_lines(session, tb.id, "SOFP")
    socie = _load_statement_lines(session, tb.id, "SOCIE")
    if not sopl and not sofp and not socie:
        raise ValueError("Statements must be generated before export")

    variance = _load_variance(session, tb.id)
    risk_flags = _load_risk_flags(session, tb.id) if include_risk else []
    mappings = _load_mappings(session, tb.company_id) if include_mapping else []

    branding = ExportBranding(
        client_name=company.name,
        period_end=tb.period_end,
        generated_at=datetime.now(timezone.utc),
        functional_currency=company.functional_currency,
        organisation_name=organisation.name,
    )
    package = ExportPackage(
        sopl=sopl,
        sofp=sofp,
        socie=socie,
        variance=variance,
        risk_flags=risk_flags,
        mappings=mappings,
    )
    return branding, package, organisation


def _load_statement_lines(
    session: Session,
    tb_id: uuid.UUID,
    statement_type: str,
) -> list[StatementLineItemRecord]:
    fs = session.execute(
        select(FinancialStatement).where(
            FinancialStatement.tb_id == tb_id,
            FinancialStatement.statement_type == statement_type,
        )
    ).scalar_one_or_none()
    if fs is None:
        return []
    lines = list(
        session.scalars(
            select(StatementLineItem)
            .where(StatementLineItem.statement_id == fs.id)
            .order_by(StatementLineItem.display_order)
        ).all()
    )
    return [
        StatementLineItemRecord(
            line_item_code=line.line_item_code,
            line_item_name=line.line_item_name,
            amount=Decimal(line.amount),
            is_subtotal=line.is_subtotal,
            display_order=line.display_order,
            source_account_ids=list(line.source_account_ids or []),
        )
        for line in lines
    ]


def _load_variance(
    session: Session, tb_id: uuid.UUID
) -> VarianceAnalysisResult | None:
    row = session.execute(
        select(VarianceAnalysis)
        .where(VarianceAnalysis.tb_id == tb_id)
        .order_by(VarianceAnalysis.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        return None
    return VarianceAnalysisResult.model_validate(row.items)


def _load_risk_flags(session: Session, tb_id: uuid.UUID) -> list[RiskFlagRecord]:
    flags = list(
        session.scalars(
            select(RiskFlag)
            .where(RiskFlag.tb_id == tb_id)
            .order_by(RiskFlag.created_at.asc())
        ).all()
    )
    records: list[RiskFlagRecord] = []
    for flag in flags:
        affected: list[AffectedAccount] | None = None
        raw = flag.affected_accounts
        if isinstance(raw, list):
            affected = [AffectedAccount.model_validate(item) for item in raw]
        records.append(
            RiskFlagRecord(
                rule_name=flag.rule_name,
                severity=flag.severity,  # type: ignore[arg-type]
                description=flag.description,
                affected_accounts=affected,
                recommended_action=flag.recommended_action,
            )
        )
    return records


def _load_mappings(session: Session, company_id: uuid.UUID) -> list[MappingResult]:
    rows = list(
        session.scalars(
            select(AccountMapping)
            .where(
                AccountMapping.company_id == company_id,
                AccountMapping.is_confirmed.is_(True),
            )
            .order_by(AccountMapping.source_code.asc())
        ).all()
    )
    return [
        MappingResult(
            source_code=row.source_code or "",
            source_name=row.source_name,
            canonical_line=row.canonical_line,
            confidence=Decimal(row.confidence) if row.confidence is not None else None,
            method=row.method,  # type: ignore[arg-type]
        )
        for row in rows
    ]
