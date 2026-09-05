"""Trial balance upload, mapping, validation, and statements routes (§10.2 / §10.3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SyncSessionLocal, aset_rls_org_id, set_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.account_mapping import AccountMapping
from app.models.client import Client
from app.models.company import Company
from app.models.financial_statement import FinancialStatement
from app.models.processing_job import ProcessingJob
from app.models.statement_line_item import StatementLineItem
from app.models.trial_balance import TrialBalance
from app.schemas.trial_balance import ValidationResults
from app.services.statements import (
    MappedStatementAccount,
    StatementLineItemRecord,
    build_statements,
    iter_nil_filtered_face_lines,
)
from app.services.archival import archive_trial_balance_user_deleted
from app.schemas.materiality import MaterialitySuggestionResponse
from app.services.materiality import suggest_materiality
from app.services.ownership import get_owned_company
from app.services.performance import (
    METRIC_CODES,
    build_period_metrics,
    expense_share_amounts,
    select_history_periods,
)
from app.services.llm import MAPPING_TIE_BREAKER_CANONICAL_LINES
from app.services.prior_period import find_prior_trial_balance
from app.services.tb_pipeline import parsed_rows_from_tb, run_parse_and_map_job
from app.services.validator import SimpleMappedAccount, validate_trial_balance

_EXPENSE_LABELS: dict[str, str] = {
    "cost_of_sales": "Cost of sales",
    "operating_expenses": "Operating expenses",
    "depreciation": "Depreciation",
}

router = APIRouter(prefix="/trial-balances", tags=["trial-balances"])

BLOCKING_CHECKS = frozenset({"tb_integrity", "balance_sheet_balance", "net_assets"})


# --- response schemas (§10.3) -------------------------------------------------


class UploadAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    job_id: uuid.UUID
    status: Literal["pending"]
    message: str


class JobStatusItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_type: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    status: str
    progress_pct: int
    current_step: str | None = None
    error_message: str | None = None
    jobs: list[JobStatusItem]


class MappingItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    source_code: str | None
    source_name: str
    suggested_canonical_line: str
    confidence: float | None
    method: str
    is_confirmed: bool
    is_ignored: bool


class MappingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    mapping_rate: float
    unmapped_count: int
    mappings: list[MappingItemResponse]


class MappingConfirmItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    canonical_line: str | None = None
    is_confirmed: bool = True
    is_ignored: bool = False


class MappingConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mappings: list[MappingConfirmItem] | None = None


class MappingConfirmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    confirmed_count: int
    validation_job_id: uuid.UUID
    status: str


class ValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    all_passed: bool
    can_generate_statements: bool
    checks: list[dict[str, Any]]


class StatementLineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    line_item_code: str
    line_item_name: str
    amount: str
    is_subtotal: bool
    display_order: int
    source_account_ids: list[uuid.UUID] = Field(default_factory=list)


class StatementBlockResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_type: Literal["SOPL", "SOFP", "SOCIE"]
    generated_at: datetime
    lines: list[StatementLineResponse]


class StatementsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    company_id: uuid.UUID
    period_end: date
    functional_currency: str
    statements: list[StatementBlockResponse]


class StatementsGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    company_id: uuid.UUID
    period_end: date
    status: str
    functional_currency: str
    statements: list[StatementBlockResponse]


class TrialBalanceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    company_id: uuid.UUID
    period_end: date
    status: str
    created_at: datetime


class TrialBalanceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TrialBalanceListItem]
    total: int
    limit: int
    offset: int



class TrialBalanceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    period_end: date
    period_start: date | None = None
    status: str
    currency: str | None = None
    is_deleted: bool
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PriorPeriodPreviewResponse(BaseModel):
    """Read-only preview of which prior TB variance auto-detection would pick."""

    model_config = ConfigDict(extra="forbid")

    company_id: uuid.UUID
    company_name: str
    period_end: date
    prior_tb_id: uuid.UUID | None = None
    prior_period_end: date | None = None
    prior_status: str | None = None


class PerformancePeriodMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue: str | None = None
    gross_profit: str | None = None
    net_profit: str | None = None
    cash: str | None = None
    cost_of_sales: str | None = None
    operating_expenses: str | None = None
    depreciation: str | None = None


class PerformancePeriodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    period_end: date
    metrics: PerformancePeriodMetrics


class PerformanceExpenseShare(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal["cost_of_sales", "operating_expenses", "depreciation"]
    label: str
    amount: str


class PerformanceOverviewResponse(BaseModel):
    """Multi-period KPI series for the statements performance overview."""

    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    company_id: uuid.UUID
    period_end: date
    functional_currency: str
    period_count: int
    periods: list[PerformancePeriodResponse]
    expense_breakdown: list[PerformanceExpenseShare]


_DEFAULT_TB_PAGE = 20
_MAX_TB_PAGE = 100


# --- helpers -----------------------------------------------------------------


async def _get_owned_tb(
    session: AsyncSession,
    *,
    tb_id: uuid.UUID,
    org_id: uuid.UUID,
) -> TrialBalance:
    result = await session.execute(
        select(TrialBalance)
        .join(Company, Company.id == TrialBalance.company_id)
        .join(Client, Client.id == Company.client_id)
        .where(
            TrialBalance.id == tb_id,
            TrialBalance.is_deleted.is_(False),
            Client.org_id == org_id,
            Client.is_deleted.is_(False),
            Company.is_deleted.is_(False),
        )
    )
    tb = result.scalar_one_or_none()
    if tb is None:
        raise HTTPException(status_code=404, detail="Trial balance not found")
    return tb


async def _get_tb_functional_currency(
    session: AsyncSession,
    *,
    tb: TrialBalance,
) -> str:
    result = await session.execute(
        select(Company.functional_currency).where(Company.id == tb.company_id)
    )
    currency = result.scalar_one_or_none()
    return (currency or "GBP").upper()


def _file_extension(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith(".csv"):
        return "csv"
    raise HTTPException(status_code=400, detail="Only .xlsx and .csv files are accepted")


def _progress_for_tb(tb: TrialBalance, jobs: list[ProcessingJob]) -> tuple[int, str | None]:
    status_pct = {
        "pending": 0,
        "parsing": 15,
        "mapping": 40,
        "validating": 60,
        "generating": 80,
        "analysing": 90,
        "complete": 100,
        "failed": 100,
    }
    pct = status_pct.get(tb.status, 0)
    running = next((job for job in jobs if job.status == "running"), None)
    step = running.step if running is not None else None
    if step is None and jobs:
        latest = max(jobs, key=lambda job: job.updated_at or job.created_at)
        step = latest.step
    return pct, step


# --- routes ------------------------------------------------------------------


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=UploadAcceptedResponse,
)
async def upload_trial_balance(
    background_tasks: BackgroundTasks,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    company_id: Annotated[uuid.UUID, Form()],
    period_end: Annotated[date, Form()],
    file: Annotated[UploadFile, File()],
    currency: Annotated[str, Form()] = "GBP",
) -> UploadAcceptedResponse:
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(session, company_id=company_id, org_id=auth.org_id)

    filename = file.filename or "upload.xlsx"
    file_type = _file_extension(filename)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 50MB limit")

    upload_root = Path(settings.upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4()}.{file_type}"
    stored_path = upload_root / stored_name
    stored_path.write_bytes(content)
    file_url = f"file://{stored_path}"
    currency_code = company.functional_currency.upper()

    # UNIQUE(company_id, period_end) must not permanently block retry after a
    # failed parse: replace the failed row in place. Non-failed rows still 409.
    existing = (
        await session.execute(
            select(TrialBalance).where(
                TrialBalance.company_id == company.id,
                TrialBalance.period_end == period_end,
                TrialBalance.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()

    if existing is not None and existing.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "A trial balance already exists for this company and period_end"
                ),
                "existing_tb_id": str(existing.id),
                "existing_status": existing.status,
            },
        )

    if existing is not None and existing.status == "failed":
        tb = existing
        # Drop prior jobs / derived rows (CASCADE on tb_id FKs) before reuse.
        for child in (
            await session.execute(
                select(ProcessingJob).where(ProcessingJob.tb_id == tb.id)
            )
        ).scalars().all():
            await session.delete(child)
        for child in (
            await session.execute(
                select(FinancialStatement).where(FinancialStatement.tb_id == tb.id)
            )
        ).scalars().all():
            await session.delete(child)
        await session.flush()
        tb.file_url = file_url
        tb.file_type = file_type
        tb.file_size_bytes = len(content)
        tb.file_hash = None
        tb.raw_data = None
        tb.parsed_data = None
        tb.validation_results = None
        tb.error_message = None
        tb.status = "pending"
        tb.currency = currency_code
    else:
        tb = TrialBalance(
            company_id=company.id,
            period_end=period_end,
            file_url=file_url,
            file_type=file_type,
            file_size_bytes=len(content),
            status="pending",
            # Company.functional_currency is authoritative — ignore mismatched form values.
            currency=currency_code,
        )
        session.add(tb)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": (
                        "A trial balance already exists for this company and period_end"
                    ),
                },
            ) from exc

    parse_job = ProcessingJob(
        tb_id=tb.id,
        job_type="parse",
        status="pending",
        step="Queued for parsing",
        progress_pct=0,
    )
    map_job = ProcessingJob(
        tb_id=tb.id,
        job_type="map",
        status="pending",
        step="Queued for mapping",
        progress_pct=0,
    )
    session.add(parse_job)
    session.add(map_job)
    await session.flush()
    # Commit before scheduling BackgroundTasks so the worker session can see rows.
    await session.commit()

    background_tasks.add_task(
        run_parse_and_map_job,
        tb_id=tb.id,
        org_id=auth.org_id,
        parse_job_id=parse_job.id,
        map_job_id=map_job.id,
        openai_client=None,
    )

    return UploadAcceptedResponse(
        tb_id=tb.id,
        job_id=parse_job.id,
        status="pending",
        message="Upload accepted. Processing will begin shortly.",
    )


@router.get("", response_model=TrialBalanceListResponse)
async def list_trial_balances(
    company_id: Annotated[uuid.UUID, Query()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=_MAX_TB_PAGE)] = _DEFAULT_TB_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TrialBalanceListResponse:
    """List trial balances for a company (paginated). Cross-org company_id → 404."""
    await aset_rls_org_id(session, auth.org_id)
    await get_owned_company(session, company_id=company_id, org_id=auth.org_id)

    base = select(TrialBalance).where(
        TrialBalance.company_id == company_id,
        TrialBalance.is_deleted.is_(False),
    )
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    result = await session.execute(
        base.order_by(TrialBalance.period_end.desc(), TrialBalance.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(result.scalars().all())
    return TrialBalanceListResponse(
        items=[
            TrialBalanceListItem(
                id=tb.id,
                company_id=tb.company_id,
                period_end=tb.period_end,
                status=tb.status,
                created_at=tb.created_at,
            )
            for tb in items
        ],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.get("/prior-period-preview", response_model=PriorPeriodPreviewResponse)
async def preview_prior_period(
    company_id: Annotated[uuid.UUID, Query()],
    period_end: Annotated[date, Query()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PriorPeriodPreviewResponse:
    """Lightweight check: which prior TB would auto-detection use for this upload?

    Same rule as variance auto-detect (§6.2): most recent same-company TB with
    period_end strictly before the candidate period_end. Read-only — does not
    create or link anything.
    """
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(
        session, company_id=company_id, org_id=auth.org_id
    )
    prior = await find_prior_trial_balance(
        session,
        company_id=company.id,
        before_period_end=period_end,
    )
    if prior is None:
        return PriorPeriodPreviewResponse(
            company_id=company.id,
            company_name=company.name,
            period_end=period_end,
        )
    return PriorPeriodPreviewResponse(
        company_id=company.id,
        company_name=company.name,
        period_end=period_end,
        prior_tb_id=prior.id,
        prior_period_end=prior.period_end,
        prior_status=prior.status,
    )



@router.delete(
    "/{tb_id}",
    status_code=status.HTTP_200_OK,
    response_model=TrialBalanceResponse,
)
async def soft_delete_trial_balance(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TrialBalance:
    """Soft delete + archived_records snapshot in the same transaction (§12.2)."""
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    company = await session.get(Company, tb.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Trial balance not found")

    now = datetime.now(timezone.utc)
    tb.is_deleted = True
    tb.deleted_at = now
    await session.flush()
    await session.refresh(tb)
    await archive_trial_balance_user_deleted(
        session,
        tb=tb,
        org_id=auth.org_id,
        client_id=company.client_id,
        archived_by_user_id=auth.user_id,
        archived_at=now,
    )
    return tb


@router.get("/{tb_id}/status", response_model=StatusResponse)
async def get_trial_balance_status(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatusResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    jobs_result = await session.execute(
        select(ProcessingJob)
        .where(ProcessingJob.tb_id == tb.id)
        .order_by(ProcessingJob.created_at)
    )
    jobs = list(jobs_result.scalars().all())
    progress_pct, current_step = _progress_for_tb(tb, jobs)
    return StatusResponse(
        tb_id=tb.id,
        status=tb.status,
        progress_pct=progress_pct,
        current_step=current_step,
        error_message=tb.error_message,
        jobs=[
            JobStatusItem(
                job_type=job.job_type,
                status=job.status,
                started_at=job.started_at,
                completed_at=job.completed_at,
            )
            for job in jobs
        ],
    )


@router.get("/{tb_id}/mapping", response_model=MappingResponse)
async def get_trial_balance_mapping(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MappingResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    rows = parsed_rows_from_tb(tb)
    codes_names = {(row.account_code, row.account_name) for row in rows}

    mappings_result = await session.execute(
        select(AccountMapping).where(AccountMapping.company_id == tb.company_id)
    )
    all_mappings = list(mappings_result.scalars().all())
    relevant = [
        mapping
        for mapping in all_mappings
        if (mapping.source_code or "", mapping.source_name) in codes_names
        or not codes_names
    ]
    if codes_names:
        relevant = [
            mapping
            for mapping in all_mappings
            if (mapping.source_code or "", mapping.source_name) in codes_names
        ]

    unmapped_count = sum(
        1
        for mapping in relevant
        if mapping.canonical_line == "unmapped" and not mapping.is_ignored
    )
    total = len(relevant) or 1
    mapped = sum(
        1
        for mapping in relevant
        if mapping.canonical_line != "unmapped" and not mapping.is_ignored
    )
    return MappingResponse(
        tb_id=tb.id,
        mapping_rate=round(mapped / total, 4),
        unmapped_count=unmapped_count,
        mappings=[
            MappingItemResponse(
                id=mapping.id,
                source_code=mapping.source_code,
                source_name=mapping.source_name,
                suggested_canonical_line=mapping.canonical_line,
                confidence=float(mapping.confidence)
                if mapping.confidence is not None
                else None,
                method=mapping.method,
                is_confirmed=mapping.is_confirmed,
                is_ignored=mapping.is_ignored,
            )
            for mapping in relevant
        ],
    )


@router.post("/{tb_id}/mapping/confirm", response_model=MappingConfirmResponse)
async def confirm_trial_balance_mapping(
    tb_id: uuid.UUID,
    body: MappingConfirmRequest,
    background_tasks: BackgroundTasks,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MappingConfirmResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    mappings_result = await session.execute(
        select(AccountMapping).where(AccountMapping.company_id == tb.company_id)
    )
    by_id = {mapping.id: mapping for mapping in mappings_result.scalars().all()}

    confirmed_count = 0
    if body.mappings is not None:
        if not body.mappings:
            raise HTTPException(
                status_code=400,
                detail="mappings must not be empty; send one item per account row",
            )
        for item in body.mappings:
            mapping = by_id.get(item.id)
            if mapping is None:
                raise HTTPException(status_code=404, detail="Mapping not found")
            if item.canonical_line is None:
                raise HTTPException(
                    status_code=400,
                    detail="canonical_line is required for each mapping item",
                )
            if item.is_confirmed and not item.is_ignored and item.canonical_line == "unmapped":
                raise HTTPException(
                    status_code=400,
                    detail="Resolve all unmapped accounts before confirming. Choose a canonical line for every row.",
                )
            if item.canonical_line not in MAPPING_TIE_BREAKER_CANONICAL_LINES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f'Invalid canonical_line "{item.canonical_line}". '
                        "Must be one of the Appendix A account categories."
                    ),
                )
            mapping.canonical_line = item.canonical_line
            mapping.is_confirmed = item.is_confirmed
            mapping.is_ignored = item.is_ignored
            # Human is setting the value — method is manual from this point.
            if item.is_confirmed and not item.is_ignored:
                mapping.method = "manual"
                mapping.confidence = Decimal("1.00")
            confirmed_count += 1
    else:
        rows = parsed_rows_from_tb(tb)
        keys = {(row.account_code, row.account_name) for row in rows}
        for mapping in by_id.values():
            if (mapping.source_code or "", mapping.source_name) not in keys:
                continue
            if mapping.canonical_line == "unmapped":
                continue
            mapping.is_confirmed = True
            mapping.method = "manual"
            mapping.confidence = Decimal("1.00")
            confirmed_count += 1

    validate_job = ProcessingJob(
        tb_id=tb.id,
        job_type="validate",
        status="pending",
        step="Queued for validation",
        progress_pct=0,
    )
    session.add(validate_job)
    tb.status = "validating"
    await session.flush()
    await session.commit()

    background_tasks.add_task(
        run_validation_job,
        tb_id=tb.id,
        org_id=auth.org_id,
        validate_job_id=validate_job.id,
    )

    return MappingConfirmResponse(
        tb_id=tb.id,
        confirmed_count=confirmed_count,
        validation_job_id=validate_job.id,
        status="validating",
    )


def run_validation_job(
    *,
    tb_id: uuid.UUID,
    org_id: uuid.UUID,
    validate_job_id: uuid.UUID,
) -> None:
    with SyncSessionLocal() as session:
        try:
            set_rls_org_id(session, org_id)
            tb = session.get(TrialBalance, tb_id)
            job = session.get(ProcessingJob, validate_job_id)
            if tb is None or job is None:
                return
            from datetime import timezone

            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.step = "Running validation checks"
            tb.status = "validating"
            session.commit()

            set_rls_org_id(session, org_id)
            tb = session.get(TrialBalance, tb_id)
            job = session.get(ProcessingJob, validate_job_id)
            assert tb is not None and job is not None

            accounts = _mapped_accounts_for_tb(session, tb)
            results = validate_trial_balance(accounts)
            tb.validation_results = results.to_jsonb()
            job.status = "complete"
            job.progress_pct = 100
            job.completed_at = datetime.now(timezone.utc)
            job.step = "Validation complete"
            session.commit()
        except Exception as exc:
            session.rollback()
            with SyncSessionLocal() as err_session:
                set_rls_org_id(err_session, org_id)
                tb = err_session.get(TrialBalance, tb_id)
                job = err_session.get(ProcessingJob, validate_job_id)
                if tb is not None:
                    tb.status = "failed"
                    tb.error_message = str(exc)
                if job is not None:
                    job.status = "failed"
                    job.error_message = str(exc)
                err_session.commit()


def _mapped_accounts_for_tb(session: Session, tb: TrialBalance) -> list[SimpleMappedAccount]:
    rows = parsed_rows_from_tb(tb)
    mappings = list(
        session.scalars(
            select(AccountMapping).where(AccountMapping.company_id == tb.company_id)
        ).all()
    )
    by_key = {
        (mapping.source_code or "", mapping.source_name): mapping for mapping in mappings
    }
    accounts: list[SimpleMappedAccount] = []
    for row in rows:
        mapping = by_key.get((row.account_code, row.account_name))
        canonical = mapping.canonical_line if mapping is not None else "unmapped"
        if canonical == "unmapped":
            continue
        accounts.append(
            SimpleMappedAccount(
                account_code=row.account_code,
                account_name=row.account_name,
                debit=row.debit,
                credit=row.credit,
                net_balance=row.net_balance,
                canonical_line=canonical,
            )
        )
    return accounts


@router.get("/{tb_id}/validation", response_model=ValidationResponse)
async def get_trial_balance_validation(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ValidationResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    if not tb.validation_results:
        raise HTTPException(status_code=404, detail="Validation results not available yet")
    results = ValidationResults.model_validate(tb.validation_results)
    return ValidationResponse(
        tb_id=tb.id,
        all_passed=results.all_passed,
        can_generate_statements=results.can_generate_statements,
        checks=[check.model_dump(mode="json", exclude_none=True) for check in results.checks],
    )


@router.post("/{tb_id}/statements", response_model=StatementsGenerateResponse)
async def generate_statements(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatementsGenerateResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    if not tb.validation_results:
        raise HTTPException(status_code=400, detail="Confirm mapping and run validation first")
    results = ValidationResults.model_validate(tb.validation_results)
    if not results.can_generate_statements:
        raise HTTPException(
            status_code=400,
            detail="Blocking validation checks have not passed",
        )

    # Run synchronously for MVP so GET immediately reflects results; still record a job.
    statements_job = ProcessingJob(
        tb_id=tb.id,
        job_type="statements",
        status="running",
        step="Generating SOPL/SOFP/SOCIE",
        progress_pct=50,
    )
    session.add(statements_job)
    tb.status = "generating"
    await session.flush()

    # Build with sync session under same RLS org for mapper-style access.
    payload = await _generate_and_persist_statements(session, tb=tb, org_id=auth.org_id)
    statements_job.status = "complete"
    statements_job.progress_pct = 100
    from datetime import timezone

    statements_job.completed_at = datetime.now(timezone.utc)
    tb.status = "complete"
    await session.flush()

    return StatementsGenerateResponse(
        tb_id=tb.id,
        company_id=tb.company_id,
        period_end=tb.period_end,
        status="complete",
        functional_currency=await _get_tb_functional_currency(session, tb=tb),
        statements=payload,
    )


async def _generate_and_persist_statements(
    session: AsyncSession,
    *,
    tb: TrialBalance,
    org_id: uuid.UUID,
) -> list[StatementBlockResponse]:
    # Use sync path for statement persistence consistency with ORM models.
    with SyncSessionLocal() as sync_session:
        set_rls_org_id(sync_session, org_id)
        sync_tb = sync_session.get(TrialBalance, tb.id)
        assert sync_tb is not None
        accounts = _statement_accounts(sync_session, sync_tb)
        sopl, sofp, socie = build_statements(accounts)

        # Replace prior statements for this TB.
        existing = list(
            sync_session.scalars(
                select(FinancialStatement).where(FinancialStatement.tb_id == sync_tb.id)
            ).all()
        )
        for statement in existing:
            sync_session.delete(statement)
        sync_session.flush()

        blocks: list[StatementBlockResponse] = []
        for statement_type, lines in (
            ("SOPL", sopl),
            ("SOFP", sofp),
            ("SOCIE", socie),
        ):
            fs = FinancialStatement(
                tb_id=sync_tb.id,
                statement_type=statement_type,
                data={"lines": [_line_to_json(line) for line in lines]},
            )
            sync_session.add(fs)
            sync_session.flush()
            # Persist the full skeleton (including nil leaves) for audit/evidence.
            # Response face lines match GET/export: omit nil leaves / empty sections.
            persisted: list[StatementLineResponse] = []
            for line in lines:
                sli = StatementLineItem(
                    statement_id=fs.id,
                    line_item_code=line.line_item_code,
                    line_item_name=line.line_item_name,
                    amount=line.amount,
                    is_subtotal=line.is_subtotal,
                    display_order=line.display_order,
                    source_account_ids=line.source_account_ids or None,
                )
                sync_session.add(sli)
                sync_session.flush()
                persisted.append(
                    StatementLineResponse(
                        id=sli.id,
                        line_item_code=sli.line_item_code,
                        line_item_name=sli.line_item_name,
                        amount=str(sli.amount),
                        is_subtotal=sli.is_subtotal,
                        display_order=sli.display_order,
                        source_account_ids=list(sli.source_account_ids or []),
                    )
                )
            display_lines = iter_nil_filtered_face_lines(persisted)
            blocks.append(
                StatementBlockResponse(
                    statement_type=statement_type,  # type: ignore[arg-type]
                    generated_at=fs.generated_at,
                    lines=[
                        line.model_copy(update={"display_order": index})
                        for index, line in enumerate(display_lines, start=1)
                    ],
                )
            )
        sync_session.commit()
        return blocks


def _line_to_json(line: StatementLineItemRecord) -> dict[str, Any]:
    return {
        "line_item_code": line.line_item_code,
        "line_item_name": line.line_item_name,
        "amount": str(line.amount),
        "is_subtotal": line.is_subtotal,
        "display_order": line.display_order,
        "source_account_ids": [str(item) for item in line.source_account_ids],
    }


def _statement_accounts(
    session: Session, tb: TrialBalance
) -> list[MappedStatementAccount]:
    rows = parsed_rows_from_tb(tb)
    mappings = list(
        session.scalars(
            select(AccountMapping).where(
                AccountMapping.company_id == tb.company_id,
                AccountMapping.is_confirmed.is_(True),
            )
        ).all()
    )
    by_key = {
        (mapping.source_code or "", mapping.source_name): mapping for mapping in mappings
    }
    accounts: list[MappedStatementAccount] = []
    for row in rows:
        mapping = by_key.get((row.account_code, row.account_name))
        if mapping is None or mapping.canonical_line == "unmapped":
            continue
        accounts.append(
            MappedStatementAccount(
                id=mapping.id,
                account_code=row.account_code,
                net_balance=row.net_balance,
                canonical_line=mapping.canonical_line,
            )
        )
    return accounts


@router.get("/{tb_id}/statements", response_model=StatementsResponse)
async def get_statements(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatementsResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    result = await session.execute(
        select(FinancialStatement)
        .where(FinancialStatement.tb_id == tb.id)
        .order_by(FinancialStatement.statement_type)
    )
    statements = list(result.scalars().all())
    if not statements:
        raise HTTPException(status_code=404, detail="Statements not generated yet")

    blocks: list[StatementBlockResponse] = []
    for fs in statements:
        lines_result = await session.execute(
            select(StatementLineItem)
            .where(StatementLineItem.statement_id == fs.id)
            .order_by(StatementLineItem.display_order)
        )
        lines = list(lines_result.scalars().all())
        lines = iter_nil_filtered_face_lines(lines)
        blocks.append(
            StatementBlockResponse(
                statement_type=fs.statement_type,  # type: ignore[arg-type]
                generated_at=fs.generated_at,
                lines=[
                    StatementLineResponse(
                        id=line.id,
                        line_item_code=line.line_item_code,
                        line_item_name=line.line_item_name,
                        amount=str(line.amount),
                        is_subtotal=line.is_subtotal,
                        display_order=index,
                        source_account_ids=list(line.source_account_ids or []),
                    )
                    for index, line in enumerate(lines, start=1)
                ],
            )
        )
    return StatementsResponse(
        tb_id=tb.id,
        company_id=tb.company_id,
        period_end=tb.period_end,
        functional_currency=await _get_tb_functional_currency(session, tb=tb),
        statements=blocks,
    )


@router.get(
    "/{tb_id}/performance-overview",
    response_model=PerformanceOverviewResponse,
)
async def get_performance_overview(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PerformanceOverviewResponse:
    """Multi-period KPI / chart series from generated statements for this company.

    Returns every historical trial balance (up to the soft cap) that already has
    statements, as of the current TB's period_end. One period is valid — charts
    simply render what is available.
    """
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    current_fs = await session.execute(
        select(FinancialStatement.id).where(FinancialStatement.tb_id == tb.id).limit(1)
    )
    if current_fs.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Statements not generated yet")

    history_rows = await session.execute(
        select(
            TrialBalance.id,
            TrialBalance.period_end,
            StatementLineItem.line_item_code,
            StatementLineItem.amount,
        )
        .join(FinancialStatement, FinancialStatement.tb_id == TrialBalance.id)
        .join(
            StatementLineItem,
            StatementLineItem.statement_id == FinancialStatement.id,
        )
        .where(
            TrialBalance.company_id == tb.company_id,
            TrialBalance.is_deleted.is_(False),
            TrialBalance.period_end <= tb.period_end,
            StatementLineItem.line_item_code.in_(METRIC_CODES),
        )
        .order_by(TrialBalance.period_end.asc(), TrialBalance.id.asc())
    )

    by_tb: dict[uuid.UUID, dict[str, Any]] = {}
    for row_tb_id, period_end, code, amount in history_rows.all():
        bucket = by_tb.setdefault(
            row_tb_id,
            {"period_end": period_end, "amounts": {}},
        )
        bucket["amounts"].setdefault(code, Decimal(amount))

    built = [
        build_period_metrics(
            tb_id=row_tb_id,
            period_end=payload["period_end"],
            line_amounts=payload["amounts"],
        )
        for row_tb_id, payload in by_tb.items()
    ]
    periods = select_history_periods(built, as_of=tb.period_end)
    if not periods:
        raise HTTPException(status_code=404, detail="Statements not generated yet")

    current_metrics = next(
        (p.metrics for p in periods if p.tb_id == tb.id),
        periods[-1].metrics,
    )
    expense_shares = expense_share_amounts(current_metrics)

    def _fmt(value: Decimal | None) -> str | None:
        return f"{value:.2f}" if value is not None else None

    return PerformanceOverviewResponse(
        tb_id=tb.id,
        company_id=tb.company_id,
        period_end=tb.period_end,
        functional_currency=await _get_tb_functional_currency(session, tb=tb),
        period_count=len(periods),
        periods=[
            PerformancePeriodResponse(
                tb_id=period.tb_id,
                period_end=period.period_end,
                metrics=PerformancePeriodMetrics(
                    revenue=_fmt(period.metrics.get("revenue")),
                    gross_profit=_fmt(period.metrics.get("gross_profit")),
                    net_profit=_fmt(period.metrics.get("net_profit")),
                    cash=_fmt(period.metrics.get("cash")),
                    cost_of_sales=_fmt(period.metrics.get("cost_of_sales")),
                    operating_expenses=_fmt(period.metrics.get("operating_expenses")),
                    depreciation=_fmt(period.metrics.get("depreciation")),
                ),
            )
            for period in periods
        ],
        expense_breakdown=[
            PerformanceExpenseShare(
                code=code,  # type: ignore[arg-type]
                label=_EXPENSE_LABELS[code],
                amount=f"{amount:.2f}",
            )
            for code, amount in expense_shares.items()
        ],
    )


@router.get(
    "/{tb_id}/materiality-suggestion",
    response_model=MaterialitySuggestionResponse,
)
async def get_materiality_suggestion(
    tb_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaterialitySuggestionResponse:
    """Soft ISA 320-style materiality suggestion from generated statement figures."""
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)
    company = await get_owned_company(
        session, company_id=tb.company_id, org_id=auth.org_id
    )

    statements_result = await session.execute(
        select(FinancialStatement).where(FinancialStatement.tb_id == tb.id)
    )
    statements = list(statements_result.scalars().all())
    if not statements:
        raise HTTPException(status_code=404, detail="Statements not generated yet")

    sopl_lines: list[StatementLineItem] = []
    sofp_lines: list[StatementLineItem] = []
    for fs in statements:
        lines_result = await session.execute(
            select(StatementLineItem)
            .where(StatementLineItem.statement_id == fs.id)
            .order_by(StatementLineItem.display_order)
        )
        lines = list(lines_result.scalars().all())
        if fs.statement_type == "SOPL":
            sopl_lines = lines
        elif fs.statement_type == "SOFP":
            sofp_lines = lines

    company_type = (
        company.company_type
        if company.company_type in ("trading", "holding")
        else "trading"
    )
    suggestion = suggest_materiality(
        company_type=company_type,  # type: ignore[arg-type]
        current_pct=Decimal(company.materiality_threshold_pct),
        current_abs=Decimal(company.materiality_threshold_abs),
        sopl_lines=sopl_lines,
        sofp_lines=sofp_lines,
        dismissed=company.materiality_suggestion_dismissed_at is not None,
    )
    return MaterialitySuggestionResponse(
        tb_id=tb.id,
        company_id=company.id,
        available=suggestion.available,
        message=suggestion.message,
        company_type=suggestion.company_type,
        benchmark_basis=suggestion.benchmark_basis,
        benchmark_amount=(
            f"{suggestion.benchmark_amount:.2f}"
            if suggestion.benchmark_amount is not None
            else None
        ),
        range_pct_low=(
            f"{suggestion.range_pct_low:.2f}"
            if suggestion.range_pct_low is not None
            else None
        ),
        range_pct_high=(
            f"{suggestion.range_pct_high:.2f}"
            if suggestion.range_pct_high is not None
            else None
        ),
        suggested_pct=(
            f"{suggestion.suggested_pct:.2f}"
            if suggestion.suggested_pct is not None
            else None
        ),
        suggested_abs=(
            f"{suggestion.suggested_abs:.2f}"
            if suggestion.suggested_abs is not None
            else None
        ),
        current_pct=f"{suggestion.current_pct:.2f}",
        current_abs=f"{suggestion.current_abs:.2f}",
        dismissed=suggestion.dismissed,
        disclaimer=suggestion.disclaimer,
    )

