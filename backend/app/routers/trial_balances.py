"""Trial balance upload, mapping, validation, and statements routes (§10.2 / §10.3)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
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
)
from app.services.ownership import get_owned_company
from app.services.tb_pipeline import parsed_rows_from_tb, run_parse_and_map_job
from app.services.validator import SimpleMappedAccount, validate_trial_balance

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
    statements: list[StatementBlockResponse]


class StatementsGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tb_id: uuid.UUID
    status: str
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
            Client.org_id == org_id,
            Client.is_deleted.is_(False),
            Company.is_deleted.is_(False),
        )
    )
    tb = result.scalar_one_or_none()
    if tb is None:
        raise HTTPException(status_code=404, detail="Trial balance not found")
    return tb


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

    tb = TrialBalance(
        company_id=company.id,
        period_end=period_end,
        file_url=f"file://{stored_path}",
        file_type=file_type,
        file_size_bytes=len(content),
        status="pending",
        currency=currency.upper(),
    )
    session.add(tb)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A trial balance already exists for this company and period_end",
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

    base = select(TrialBalance).where(TrialBalance.company_id == company_id)
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
        status="complete",
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
            line_responses: list[StatementLineResponse] = []
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
                line_responses.append(
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
            blocks.append(
                StatementBlockResponse(
                    statement_type=statement_type,  # type: ignore[arg-type]
                    generated_at=fs.generated_at,
                    lines=line_responses,
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
                        display_order=line.display_order,
                        source_account_ids=list(line.source_account_ids or []),
                    )
                    for line in lines
                ],
            )
        )
    return StatementsResponse(tb_id=tb.id, statements=blocks)
