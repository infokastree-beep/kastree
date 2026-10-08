"""Year ends, immutable trial-balance versions, and the prior-year gate.

Parsing runs in the worker (`tb_import_worker`), not in this request handler.
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import aset_rls_org_id
from app.dependencies import (
    AuthContext,
    enforce_product2_production_access,
    get_db_session,
    require_client_admin,
    require_member_work,
    require_reader,
)
from app.models.company import Company
from app.models.fa_version import FixedAssetLine, FixedAssetVersion
from app.models.source_document import SourceDocument
from app.models.tb_version import TrialBalanceLine, TrialBalanceVersion
from app.schemas.company_details import (
    ApprovalWrite,
    CompanyDetailsResponse,
    CompanyDetailsWrite,
)
from app.schemas.report_setup import (
    ReportingFrameworkList,
    ReportSetupResponse,
    ReportSetupWrite,
)
from app.schemas.statutory_preview import PreviewChildOut, StatutoryPreviewResponse
from app.schemas.year_end import (
    FixedAssetLineOut,
    FixedAssetTotalOut,
    FixedAssetVersionCreate,
    FixedAssetVersionResponse,
    MappingConfirmRequest,
    MappingConfirmResponse,
    MappingLineOut,
    PriorYearConfirmRequest,
    PriorYearLineOut,
    PriorYearResponse,
    EvidenceResponse,
    ReconciliationCheckOut,
    ReconciliationGateResponse,
    ReconciliationResponse,
    StatementResponse,
    SizeEligibilityRequest,
    SizeEligibilityResponse,
    AdoptedTrialBalanceResponse,
    AdoptableTrialBalanceList,
    AdoptableTrialBalanceOut,
    AdoptTrialBalanceRequest,
    CanonicalLinesResponse,
    CarriedMappingOut,
    StatutorySublineConfirmRequest,
    StatutorySublineReviewResponse,
    StatutorySublineRowOut,
    TrialBalanceLineOut,
    TrialBalanceLinesResponse,
    TrialBalanceVersionCreate,
    TrialBalanceVersionResponse,
    YearEndCreateRequest,
    YearEndResponse,
    AdjustmentPostRequest,
    AdjustmentPostResponse,
    DashboardResponse,
    DashboardCheckOut,
    DisclosureAnswerRequest,
    DisclosureAnswerResponse,
    DraftMutationRequest,
    DraftStatusResponse,
    WorkingDraftResponse,
    FinaliseResponse,
    NewDraftVersionResponse,
    RenderJobResponse,
    amount_text,
)
from app.services.ownership import get_owned_company
from app.services.size_eligibility import (
    SizeEligibilityRejected,
    YearSize,
    assess_size,
    exact_amount,
    record_size_assessment,
)
from app.services.prior_year import (
    PriorYearRejected,
    confirm_prior_year,
    mark_first_financial_period,
    reconciliation_gate,
)
from app.services.adopted_trial_balance import (
    SublineChoice,
    SublineReviewRow,
    adopt_confirmed_trial_balance,
    confirm_statutory_sublines,
    list_adoptable_trial_balances,
    mapping_notice_for,
    reconcile_adopted,
    review_statutory_sublines,
)
from app.services.reconciliation import (
    ReconciliationRejected,
    ReconciliationReport,
    confirm_mappings,
    reconcile_version,
    statutory_lines,
)
from app.services.draft_workflow import (
    Dashboard,
    DraftRejected,
    PostedLine,
    acknowledge_mappings,
    dashboard_for_draft,
    finalise_draft,
    frozen_snapshot,
    lock_draft,
    new_version_from_locked,
    post_adjustment,
    recompute_draft,
    set_disclosure_answer,
    start_new_report,
)
from app.services.render_jobs import (
    DOCX_MEDIA,
    find_docx_job,
    insert_docx_job,
    job_for_version,
)
from app.services.source_storage import SourceObjectStorage, get_source_storage
from app.services.tb_import_worker import run_tb_import_job
from app.services.company_details import (
    CompanyDetailsRejected,
    company_details_response,
    save_approval_details,
    save_company_details,
)
from app.services.report_setup import (
    framework_list,
    report_setup_response,
    save_report_setup,
)
from app.services.statutory_evidence import evidence_for_version
from app.services.statutory_present import evidence_response, statement_response
from app.services.statutory_compose import (
    PREVIEW_CONTENT_SECURITY_POLICY,
    compose_year_end_pdf,
)
from app.services.statutory_preview import PreviewRejected, build_section_preview
from app.services.statutory_statements import (
    StatutoryStatements,
    statements_for_adopted,
    statements_for_version,
    write_statement_pdf,
)
from findraft.engine.notes import build_fa_grid
from findraft.engine.pack import load_manifest, pack_dir, pin_pack_version
from findraft.models.draft_version import DraftVersion
from findraft.models.render_job import RenderJob
from findraft.models.year_end import YearEnd

router = APIRouter(
    prefix="/year-ends",
    tags=["year-ends"],
    dependencies=[Depends(enforce_product2_production_access)],
)


def _idempotency_key(value: str | None) -> str:
    if value is None or not value.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")
    key = value.strip()
    if len(key) > 200 or "\n" in key or "\r" in key:
        raise HTTPException(status_code=400, detail="Idempotency-Key is invalid")
    return key


async def _owned_year_end(
    session: AsyncSession, *, year_end_id: uuid.UUID, org_id: uuid.UUID
) -> YearEnd:
    year_end = await session.get(YearEnd, year_end_id)
    if year_end is None or year_end.org_id != org_id:
        raise HTTPException(status_code=404, detail="Year end not found")
    return year_end


def _version_response(
    version: TrialBalanceVersion,
    draft_number: int | None,
    draft_id: uuid.UUID | None = None,
) -> TrialBalanceVersionResponse:
    return TrialBalanceVersionResponse(
        id=version.id,
        year_end_id=version.year_end_id,
        version_number=version.version_number,
        source_document_id=version.source_document_id,
        status=version.status,
        error_message=version.error_message,
        draft_version_number=draft_number,
        draft_id=draft_id,
    )


async def _queue_tb_import(
    session: AsyncSession,
    background_tasks: BackgroundTasks,
    *,
    org_id: uuid.UUID,
    version_id: uuid.UUID,
    version_status: str,
    storage: SourceObjectStorage,
) -> None:
    """Commit the pending row, then parse it after the 202 is returned."""
    if not settings.tb_import_background or version_status != "pending":
        return
    await session.commit()
    background_tasks.add_task(
        run_tb_import_job,
        org_id=org_id,
        version_id=version_id,
        storage=storage,
    )


async def _latest_draft_ref(
    session: AsyncSession, version_id: uuid.UUID
) -> tuple[uuid.UUID | None, int | None]:
    row = (
        await session.execute(
            select(DraftVersion.id, DraftVersion.version_number)
            .where(DraftVersion.tb_version_id == version_id)
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None, None
    return row.id, row.version_number


@router.post("", status_code=status.HTTP_201_CREATED, response_model=YearEndResponse)
async def create_year_end(
    body: YearEndCreateRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> YearEnd:
    if body.period_end < body.period_start:
        raise HTTPException(status_code=400, detail="period_end is before period_start")
    await aset_rls_org_id(session, auth.org_id)
    company = await get_owned_company(
        session, company_id=body.company_id, org_id=auth.org_id
    )
    try:
        manifest = load_manifest(
            pack_dir(body.pack_id, body.pack_version) / "pack.json"
        )
        pinned = pin_pack_version(
            {},
            manifest,
            period_start=body.period_start.isoformat(),
        )
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    year_end = YearEnd(
        org_id=company.org_id,
        company_id=company.id,
        period_start=body.period_start,
        period_end=body.period_end,
        pack_id=str(pinned["pack_id"]),
        pack_version=str(pinned["pack_version"]),
    )
    session.add(year_end)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A year end already exists for this company and period_end",
        ) from exc
    return year_end


@router.get("/canonical-lines", response_model=CanonicalLinesResponse)
async def list_canonical_lines(
    auth: Annotated[AuthContext, Depends(require_reader)],
) -> CanonicalLinesResponse:
    """Mapping targets the statutory pack accepts. No balances."""
    del auth
    return CanonicalLinesResponse(lines=sorted(statutory_lines()))


@router.get("/frameworks", response_model=ReportingFrameworkList)
async def list_reporting_frameworks(
    auth: Annotated[AuthContext, Depends(require_reader)],
) -> ReportingFrameworkList:
    """Sidebar catalogues. An unavailable framework is listed and not selectable."""
    del auth
    return framework_list()


@router.get("/{year_end_id}/report-setup", response_model=ReportSetupResponse)
async def get_report_setup(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReportSetupResponse:
    """Display settings. Defaults are not written until the practice saves."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    return report_setup_response(year_end)


@router.put("/{year_end_id}/report-setup", response_model=ReportSetupResponse)
async def put_report_setup(
    year_end_id: uuid.UUID,
    body: ReportSetupWrite,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReportSetupResponse:
    """Save display settings. Does not rebuild statements or move the trial balance."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    return await save_report_setup(
        session,
        org_id=auth.org_id,
        user_id=auth.user_id,
        year_end=year_end,
        body=body,
    )


async def _company_for_year_end(
    session: AsyncSession, *, year_end: YearEnd, org_id: uuid.UUID
) -> Company:
    return await get_owned_company(
        session, company_id=year_end.company_id, org_id=org_id
    )


@router.get("/{year_end_id}/company-details", response_model=CompanyDetailsResponse)
async def get_company_details(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyDetailsResponse:
    """Letterhead and this year's approval. Missing facts stay empty."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    company = await _company_for_year_end(
        session, year_end=year_end, org_id=auth.org_id
    )
    return company_details_response(company, year_end)


@router.put("/{year_end_id}/company-details", response_model=CompanyDetailsResponse)
async def put_company_details(
    year_end_id: uuid.UUID,
    body: CompanyDetailsWrite,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyDetailsResponse:
    """Save company letterhead. A viewer cannot. Each save is audited."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    company = await _company_for_year_end(
        session, year_end=year_end, org_id=auth.org_id
    )
    try:
        return await save_company_details(
            session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            company=company,
            year_end=year_end,
            body=body,
        )
    except CompanyDetailsRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.put("/{year_end_id}/approval", response_model=CompanyDetailsResponse)
async def put_approval_details(
    year_end_id: uuid.UUID,
    body: ApprovalWrite,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CompanyDetailsResponse:
    """Save this year's approval date and signing directors."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    company = await _company_for_year_end(
        session, year_end=year_end, org_id=auth.org_id
    )
    try:
        return await save_approval_details(
            session,
            org_id=auth.org_id,
            user_id=auth.user_id,
            company=company,
            year_end=year_end,
            body=body,
        )
    except CompanyDetailsRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{year_end_id}", response_model=YearEndResponse)
async def get_year_end(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> YearEnd:
    """Reload one year end. The draft workspace uses this address later."""
    await aset_rls_org_id(session, auth.org_id)
    return await _owned_year_end(session, year_end_id=year_end_id, org_id=auth.org_id)


@router.get("/{year_end_id}/draft", response_model=WorkingDraftResponse)
async def get_working_draft(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkingDraftResponse:
    """Latest draft for this year end, including a continuation draft."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    draft = (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.org_id == auth.org_id,
                DraftVersion.year_end_id == year_end.id,
            )
            .order_by(DraftVersion.version_number.desc())
            .limit(1)
        )
    ).first()
    if draft is None:
        raise HTTPException(
            status_code=404,
            detail="This year end has no working draft yet",
        )
    try:
        notice = await mapping_notice_for(
            session, org_id=auth.org_id, year_end=year_end, draft=draft
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    return WorkingDraftResponse(
        draft_id=draft.id,
        version_number=draft.version_number,
        status=draft.status,
        row_version=draft.row_version,
        tb_version_id=draft.tb_version_id,
        mapping_notice=notice,
        frozen=draft.is_frozen,
    )


def _subline_row(row: SublineReviewRow) -> StatutorySublineRowOut:
    confidence = row.suggestion_confidence
    return StatutorySublineRowOut(
        nominal_code=row.nominal_code,
        account_name=row.account_name,
        product1_line=row.product1_line,
        suggested_line=row.suggested_line,
        suggestion_confidence=None if confidence is None else f"{confidence:.2f}",
        statutory_line=row.statutory_line,
        choices=list(row.choices),
    )


def _subline_response(
    rows: tuple[SublineReviewRow, ...],
) -> StatutorySublineReviewResponse:
    return StatutorySublineReviewResponse(
        blocked=any(row.statutory_line is None for row in rows),
        rows=[_subline_row(row) for row in rows],
    )


def _adoption_error(exc: ReconciliationRejected) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get(
    "/{year_end_id}/adoptable-trial-balances",
    response_model=AdoptableTrialBalanceList,
)
async def get_adoptable_trial_balances(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdoptableTrialBalanceList:
    """Completed Product 1 trial balances whose confirmed mappings all carry."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    rows = await list_adoptable_trial_balances(
        session, org_id=auth.org_id, year_end=year_end
    )
    return AdoptableTrialBalanceList(
        items=[
            AdoptableTrialBalanceOut(
                id=row.id,
                period_end=row.period_end,
                currency=row.currency,
                account_count=row.account_count,
            )
            for row in rows
        ]
    )


@router.post(
    "/{year_end_id}/adopt-trial-balance",
    response_model=AdoptedTrialBalanceResponse,
)
async def post_adopt_trial_balance(
    year_end_id: uuid.UUID,
    body: AdoptTrialBalanceRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdoptedTrialBalanceResponse:
    """Select a confirmed Product 1 trial balance. Does not copy it."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        carried = await adopt_confirmed_trial_balance(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            trial_balance_id=body.trial_balance_id,
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    except DBAPIError as exc:
        message = str(exc.orig) if exc.orig is not None else str(exc)
        if "adopted trial balance" in message:
            raise HTTPException(
                status_code=400, detail="Trial balance cannot be adopted"
            ) from exc
        raise
    return AdoptedTrialBalanceResponse(
        year_end_id=year_end.id,
        trial_balance_id=body.trial_balance_id,
        lines=[
            CarriedMappingOut(
                nominal_code=line.nominal_code,
                account_name=line.account_name,
                product1_line=line.product1_line,
                canonical_line=line.canonical_line or "",
                suggested_line=line.suggested_line,
                suggestion_confidence=(
                    None
                    if line.suggestion_confidence is None
                    else f"{line.suggestion_confidence:.2f}"
                ),
            )
            for line in carried
        ],
    )


@router.get(
    "/{year_end_id}/adopted-trial-balance/reconciliation",
    response_model=ReconciliationResponse,
)
async def get_adopted_reconciliation(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReconciliationResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        report = await reconcile_adopted(session, org_id=auth.org_id, year_end=year_end)
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    return _report_response(report)


@router.get(
    "/{year_end_id}/adopted-trial-balance/statements",
    response_model=StatementResponse,
)
async def get_adopted_statements(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatementResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        document = await statements_for_adopted(
            session, org_id=auth.org_id, year_end=year_end
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    return statement_response(document)


@router.get(
    "/{year_end_id}/adopted-trial-balance/sub-lines",
    response_model=StatutorySublineReviewResponse,
)
async def get_adopted_sublines(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatutorySublineReviewResponse:
    """Sub-line review for the seven Product 1 lines that have no single home."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        rows = await review_statutory_sublines(
            session, org_id=auth.org_id, year_end=year_end
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    return _subline_response(rows)


@router.post(
    "/{year_end_id}/adopted-trial-balance/sub-lines",
    response_model=StatutorySublineReviewResponse,
)
async def post_adopted_sublines(
    year_end_id: uuid.UUID,
    body: StatutorySublineConfirmRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatutorySublineReviewResponse:
    """Remember the accountant's sub-line. The Product 1 line stays as it is."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        rows = await confirm_statutory_sublines(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            user_id=auth.user_id,
            choices=tuple(
                SublineChoice(
                    nominal_code=line.nominal_code,
                    account_name=line.account_name,
                    statutory_line=line.statutory_line,
                )
                for line in body.lines
            ),
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    return _subline_response(rows)


@router.get(
    "/{year_end_id}/statutory-preview",
    response_model=StatutoryPreviewResponse,
)
async def get_statutory_preview(
    year_end_id: uuid.UUID,
    response: Response,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    section: str,
) -> StatutoryPreviewResponse:
    """One section of the PDF HTML. A viewer may read it. Another practice is 404."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    company = await _company_for_year_end(
        session, year_end=year_end, org_id=auth.org_id
    )
    try:
        preview = await build_section_preview(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            company=company,
            section_id=section,
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    except PreviewRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    response.headers["ETag"] = f'"{preview.preview_revision}"'
    response.headers["Cache-Control"] = "private, must-revalidate"
    response.headers["Content-Security-Policy"] = PREVIEW_CONTENT_SECURITY_POLICY
    return StatutoryPreviewResponse(
        section_id=preview.section_id,
        anchor=preview.anchor,
        row_version=preview.row_version,
        preview_revision=preview.preview_revision,
        watermark=preview.watermark,
        html=preview.html,
        section_html_sha256=hashlib.sha256(
            preview.section_html.encode("utf-8")
        ).hexdigest(),
        children=[
            PreviewChildOut(
                id=child.id,
                number=child.number,
                label=child.label,
                anchor=child.anchor,
            )
            for child in preview.children
        ],
    )


@router.get("/{year_end_id}/adopted-trial-balance/statements.pdf")
async def get_adopted_statement_pdf(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        document = await statements_for_adopted(
            session, org_id=auth.org_id, year_end=year_end
        )
    except ReconciliationRejected as exc:
        raise _adoption_error(exc) from exc
    if not document.renderable or document.html is None:
        raise HTTPException(
            status_code=400,
            detail="Statutory statements are not renderable",
        )
    company = await _company_for_year_end(
        session, year_end=year_end, org_id=auth.org_id
    )
    pdf = write_statement_pdf(compose_year_end_pdf(document, year_end, company=company))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                'attachment; filename="statutory-statements-draft.pdf"'
            )
        },
    )


@router.post(
    "/{year_end_id}/trial-balance-versions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TrialBalanceVersionResponse,
)
async def create_trial_balance_version(
    year_end_id: uuid.UUID,
    body: TrialBalanceVersionCreate,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[SourceObjectStorage, Depends(get_source_storage)],
    background_tasks: BackgroundTasks,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> TrialBalanceVersionResponse:
    key = _idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    existing = (
        await session.execute(
            select(TrialBalanceVersion).where(
                TrialBalanceVersion.org_id == auth.org_id,
                TrialBalanceVersion.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.source_document_id == body.source_document_id
            and existing.year_end_id == year_end.id
        ):
            draft_id, draft_number = await _latest_draft_ref(session, existing.id)
            response = _version_response(existing, draft_number, draft_id)
            await _queue_tb_import(
                session,
                background_tasks,
                org_id=auth.org_id,
                version_id=existing.id,
                version_status=existing.status,
                storage=storage,
            )
            return response
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different import",
        )

    document = await session.get(SourceDocument, body.source_document_id)
    if (
        document is None
        or document.org_id != auth.org_id
        or document.company_id != year_end.company_id
    ):
        raise HTTPException(status_code=404, detail="Source document not found")
    if document.detected_type not in {"xlsx", "csv"}:
        raise HTTPException(
            status_code=400,
            detail="Trial balance import accepts xlsx or csv files",
        )

    await session.execute(
        text("SELECT id FROM findraft_year_ends WHERE id = :id FOR UPDATE"),
        {"id": str(year_end.id)},
    )
    current = (
        await session.execute(
            select(func.max(TrialBalanceVersion.version_number)).where(
                TrialBalanceVersion.year_end_id == year_end.id
            )
        )
    ).scalar_one_or_none()
    version = TrialBalanceVersion(
        org_id=year_end.org_id,
        company_id=year_end.company_id,
        year_end_id=year_end.id,
        version_number=(current or 0) + 1,
        source_document_id=document.id,
        status="pending",
        idempotency_key=key,
        created_by_user_id=auth.user_id,
    )
    session.add(version)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different import",
        ) from exc
    response = _version_response(version, None)
    await _queue_tb_import(
        session,
        background_tasks,
        org_id=auth.org_id,
        version_id=version.id,
        version_status=version.status,
        storage=storage,
    )
    return response


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}",
    response_model=TrialBalanceVersionResponse,
)
async def get_trial_balance_version(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TrialBalanceVersionResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await session.get(TrialBalanceVersion, version_id)
    if (
        version is None
        or version.year_end_id != year_end.id
        or version.org_id != auth.org_id
    ):
        raise HTTPException(status_code=404, detail="Trial balance version not found")
    draft_id, draft_number = await _latest_draft_ref(session, version.id)
    return _version_response(version, draft_number, draft_id)


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/lines",
    response_model=TrialBalanceLinesResponse,
)
async def list_trial_balance_lines(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TrialBalanceLinesResponse:
    """Nominal lines for mapping. Amounts are the parsed trial balance, unchanged."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    if version.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Trial balance version is not ready",
        )
    rows = (
        await session.scalars(
            select(TrialBalanceLine)
            .where(
                TrialBalanceLine.tb_version_id == version.id,
                TrialBalanceLine.org_id == auth.org_id,
            )
            .order_by(TrialBalanceLine.line_no)
        )
    ).all()
    return TrialBalanceLinesResponse(
        lines=[
            TrialBalanceLineOut(
                line_no=row.line_no,
                nominal_code=row.nominal_code,
                account_name=row.account_name,
                debit=amount_text(row.debit),
                credit=amount_text(row.credit),
                suggested_canonical_line=row.suggested_canonical_line,
                confidence=None
                if row.suggestion_confidence is None
                else amount_text(row.suggestion_confidence),
                method=row.suggestion_method,
            )
            for row in rows
        ]
    )


@router.post(
    "/{year_end_id}/prior-year",
    response_model=PriorYearResponse,
)
async def confirm_prior_year_route(
    year_end_id: uuid.UUID,
    body: PriorYearConfirmRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PriorYearResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        stored = await confirm_prior_year(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            lines=[(line.canonical_line, line.amount) for line in body.lines],
        )
    except PriorYearRejected as exc:
        code = status.HTTP_409_CONFLICT if "already validated" in exc.detail else 400
        raise HTTPException(status_code=code, detail=exc.detail) from exc
    return PriorYearResponse(
        year_end_id=year_end.id,
        prior_year_validated=year_end.prior_year_validated,
        first_financial_period=year_end.first_financial_period,
        lines=[
            PriorYearLineOut(
                canonical_line=line.canonical_line,
                amount=amount_text(line.amount),
            )
            for line in stored
        ],
    )


@router.post(
    "/{year_end_id}/first-financial-period",
    response_model=YearEndResponse,
)
async def first_financial_period(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> YearEnd:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        return await mark_first_financial_period(
            session, org_id=auth.org_id, year_end=year_end
        )
    except PriorYearRejected as exc:
        code = status.HTTP_409_CONFLICT if "already validated" in exc.detail else 400
        raise HTTPException(status_code=code, detail=exc.detail) from exc


@router.get(
    "/{year_end_id}/reconciliation-gate",
    response_model=ReconciliationGateResponse,
)
async def get_reconciliation_gate(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReconciliationGateResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    return ReconciliationGateResponse.model_validate(reconciliation_gate(year_end))


async def _owned_tb_version(
    session: AsyncSession,
    *,
    year_end: YearEnd,
    version_id: uuid.UUID,
    org_id: uuid.UUID,
) -> TrialBalanceVersion:
    version = await session.get(TrialBalanceVersion, version_id)
    if (
        version is None
        or version.org_id != org_id
        or version.year_end_id != year_end.id
    ):
        raise HTTPException(status_code=404, detail="Trial balance version not found")
    return version


def _report_response(report: ReconciliationReport) -> ReconciliationResponse:
    return ReconciliationResponse(
        blocked=report.blocked,
        build_error=report.build_error,
        checks=[
            ReconciliationCheckOut(
                code=item.code,
                severity=item.severity,
                passed=item.passed,
                message=item.message,
            )
            for item in report.checks
        ],
        net_assets=None
        if report.net_assets is None
        else amount_text(report.net_assets),
        profit=None if report.profit is None else amount_text(report.profit),
    )


@router.post(
    "/{year_end_id}/trial-balance-versions/{version_id}/mappings",
    response_model=MappingConfirmResponse,
)
async def confirm_trial_balance_mappings(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    body: MappingConfirmRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MappingConfirmResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    try:
        stored = await confirm_mappings(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            version=version,
            lines=[(line.nominal_code, line.canonical_line) for line in body.lines],
        )
    except ReconciliationRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return MappingConfirmResponse(
        tb_version_id=version.id,
        lines=[
            MappingLineOut(
                nominal_code=row.nominal_code, canonical_line=row.canonical_line
            )
            for row in stored
        ],
    )


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/reconciliation",
    response_model=ReconciliationResponse,
)
async def get_reconciliation(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReconciliationResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    try:
        report = await reconcile_version(
            session, org_id=auth.org_id, year_end=year_end, version=version
        )
    except ReconciliationRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _report_response(report)


def _pence(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="amount is not a number") from exc
    places = amount.as_tuple().exponent
    if isinstance(places, int) and places < -2:
        raise HTTPException(status_code=400, detail="amount must be in pence")
    return amount


def _draft_error(exc: DraftRejected) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _dashboard_response(board: Dashboard) -> DashboardResponse:
    return DashboardResponse(
        draft_id=board.draft_id,
        status=board.status,
        row_version=board.row_version,
        traffic=board.traffic,
        can_finalise=board.can_finalise,
        unanswered_disclosures=list(board.unanswered_disclosures),
        checks=[
            DashboardCheckOut(
                code=item.code,
                severity=item.severity,
                passed=item.passed,
                message=item.message,
            )
            for item in board.checks
        ],
    )


async def _load_statements(
    *,
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext,
    session: AsyncSession,
) -> StatutoryStatements:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    try:
        return await statements_for_version(
            session, org_id=auth.org_id, year_end=year_end, version=version
        )
    except ReconciliationRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/statements",
    response_model=StatementResponse,
)
async def get_statements(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatementResponse:
    frozen = await _frozen_for_version(
        year_end_id=year_end_id,
        version_id=version_id,
        auth=auth,
        session=session,
    )
    if frozen is not None:
        statement = frozen.get("statement")
        if not isinstance(statement, dict):
            raise HTTPException(status_code=500, detail="FINAL snapshot is missing")
        return StatementResponse.model_validate(statement)
    document = await _load_statements(
        year_end_id=year_end_id,
        version_id=version_id,
        auth=auth,
        session=session,
    )
    return statement_response(document)


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/statements.pdf",
)
async def get_statement_pdf(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    frozen = await _frozen_for_version(
        year_end_id=year_end_id,
        version_id=version_id,
        auth=auth,
        session=session,
    )
    if frozen is not None:
        html = frozen.get("html")
        if not isinstance(html, str) or not html:
            raise HTTPException(
                status_code=400,
                detail="Statutory statements are not renderable",
            )
        filename = "statutory-statements-final.pdf"
    else:
        document = await _load_statements(
            year_end_id=year_end_id,
            version_id=version_id,
            auth=auth,
            session=session,
        )
        if not document.renderable or document.html is None:
            raise HTTPException(
                status_code=400,
                detail="Statutory statements are not renderable",
            )
        year_end = await _owned_year_end(
            session, year_end_id=year_end_id, org_id=auth.org_id
        )
        company = await _company_for_year_end(
            session, year_end=year_end, org_id=auth.org_id
        )
        html = compose_year_end_pdf(document, year_end, company=company)
        filename = "statutory-statements-draft.pdf"
    pdf = write_statement_pdf(html)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/statements/evidence",
    response_model=EvidenceResponse,
)
async def get_statement_evidence(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EvidenceResponse:
    frozen = await _frozen_for_version(
        year_end_id=year_end_id,
        version_id=version_id,
        auth=auth,
        session=session,
    )
    if frozen is not None:
        evidence = frozen.get("evidence")
        if not isinstance(evidence, dict):
            raise HTTPException(status_code=500, detail="FINAL snapshot is missing")
        return EvidenceResponse.model_validate(evidence)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    try:
        graph = await evidence_for_version(
            session, org_id=auth.org_id, year_end=year_end, version=version
        )
    except ReconciliationRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return evidence_response(graph)


async def _frozen_for_version(
    *,
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: AuthContext,
    session: AsyncSession,
) -> dict[str, object] | None:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    return await frozen_snapshot(session, org_id=auth.org_id, tb_version_id=version.id)


def _fa_response(
    version: FixedAssetVersion, lines: list[FixedAssetLine]
) -> FixedAssetVersionResponse:
    total: FixedAssetTotalOut | None = None
    invariant: bool | None = None
    if version.status == "ready" and lines:
        grid = build_fa_grid(
            {
                line.asset_class: {
                    "opening_cost": line.opening_cost,
                    "additions": line.additions,
                    "disposals": line.disposals,
                    "disposals_dep": line.disposals_dep,
                    "opening_dep": line.opening_dep,
                    "charge": line.charge,
                }
                for line in lines
            }
        )
        totals = next(row for row in grid if row.get("class") == "Total")
        holds = grid[-1].get("invariant_holds")
        invariant = holds if isinstance(holds, bool) else None
        total = FixedAssetTotalOut(
            opening_cost=amount_text(totals["opening_cost"]),
            additions=amount_text(totals["additions"]),
            disposals=amount_text(totals["disposals"]),
            disposals_dep=amount_text(totals["disposals_dep"]),
            closing_cost=amount_text(totals["closing_cost"]),
            opening_dep=amount_text(totals["opening_dep"]),
            charge=amount_text(totals["charge"]),
            closing_dep=amount_text(totals["closing_dep"]),
            nbv_close=amount_text(totals["nbv_close"]),
            nbv_open=amount_text(totals["nbv_open"]),
        )
    return FixedAssetVersionResponse(
        id=version.id,
        year_end_id=version.year_end_id,
        version_number=version.version_number,
        source_document_id=version.source_document_id,
        status=version.status,
        error_message=version.error_message,
        lines=[
            FixedAssetLineOut(
                asset_class=line.asset_class,
                opening_cost=amount_text(line.opening_cost),
                additions=amount_text(line.additions),
                disposals=amount_text(line.disposals),
                disposals_dep=amount_text(line.disposals_dep),
                opening_dep=amount_text(line.opening_dep),
                charge=amount_text(line.charge),
            )
            for line in lines
        ],
        total=total,
        invariant_holds=invariant,
    )


async def _fa_lines(
    session: AsyncSession, version_id: uuid.UUID
) -> list[FixedAssetLine]:
    return list(
        (
            await session.scalars(
                select(FixedAssetLine)
                .where(FixedAssetLine.fa_version_id == version_id)
                .order_by(FixedAssetLine.line_no)
            )
        ).all()
    )


@router.post(
    "/{year_end_id}/fixed-asset-versions",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FixedAssetVersionResponse,
)
async def create_fixed_asset_version(
    year_end_id: uuid.UUID,
    body: FixedAssetVersionCreate,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> FixedAssetVersionResponse:
    key = _idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    existing = (
        await session.execute(
            select(FixedAssetVersion).where(
                FixedAssetVersion.org_id == auth.org_id,
                FixedAssetVersion.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.source_document_id == body.source_document_id
            and existing.year_end_id == year_end.id
        ):
            return _fa_response(existing, await _fa_lines(session, existing.id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different import",
        )

    document = await session.get(SourceDocument, body.source_document_id)
    if (
        document is None
        or document.org_id != auth.org_id
        or document.company_id != year_end.company_id
    ):
        raise HTTPException(status_code=404, detail="Source document not found")
    if document.detected_type not in {"xlsx", "csv"}:
        raise HTTPException(
            status_code=400,
            detail="Fixed asset import accepts xlsx or csv files",
        )

    await session.execute(
        text("SELECT id FROM findraft_year_ends WHERE id = :id FOR UPDATE"),
        {"id": str(year_end.id)},
    )
    current = (
        await session.execute(
            select(func.max(FixedAssetVersion.version_number)).where(
                FixedAssetVersion.year_end_id == year_end.id
            )
        )
    ).scalar_one_or_none()
    version = FixedAssetVersion(
        org_id=year_end.org_id,
        company_id=year_end.company_id,
        year_end_id=year_end.id,
        version_number=(current or 0) + 1,
        source_document_id=document.id,
        status="pending",
        idempotency_key=key,
        created_by_user_id=auth.user_id,
    )
    session.add(version)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key was already used for a different import",
        ) from exc
    return _fa_response(version, [])


@router.get(
    "/{year_end_id}/fixed-asset-versions/{version_id}",
    response_model=FixedAssetVersionResponse,
)
async def get_fixed_asset_version(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> FixedAssetVersionResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await session.get(FixedAssetVersion, version_id)
    if (
        version is None
        or version.year_end_id != year_end.id
        or version.org_id != auth.org_id
    ):
        raise HTTPException(status_code=404, detail="Fixed asset version not found")
    return _fa_response(version, await _fa_lines(session, version.id))


def _size_response(year_end: YearEnd) -> SizeEligibilityResponse:
    if (
        year_end.size_checked_at is None
        or year_end.size_eligible is None
        or year_end.size_current_met is None
        or year_end.size_message is None
    ):
        raise HTTPException(
            status_code=404, detail="Size eligibility has not been checked"
        )
    return SizeEligibilityResponse(
        year_end_id=year_end.id,
        eligible=year_end.size_eligible,
        current_conditions_met=year_end.size_current_met,
        preceding_conditions_met=year_end.size_preceding_met,
        message=year_end.size_message,
    )


@router.post(
    "/{year_end_id}/size-eligibility",
    response_model=SizeEligibilityResponse,
)
async def check_size_eligibility(
    year_end_id: uuid.UUID,
    body: SizeEligibilityRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SizeEligibilityResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    company = await session.get(Company, year_end.company_id)
    if company is None or company.org_id != auth.org_id:
        raise HTTPException(status_code=404, detail="Company not found")
    try:
        manifest = load_manifest(
            pack_dir(year_end.pack_id, year_end.pack_version) / "pack.json"
        )
        assessment = assess_size(
            manifest,
            company_currency=company.functional_currency,
            current=YearSize(
                turnover=exact_amount(body.current.turnover),
                balance_sheet_total=exact_amount(body.current.balance_sheet_total),
                employees=body.current.employees,
            ),
            preceding=(
                None
                if body.preceding is None
                else YearSize(
                    turnover=exact_amount(body.preceding.turnover),
                    balance_sheet_total=exact_amount(
                        body.preceding.balance_sheet_total
                    ),
                    employees=body.preceding.employees,
                )
            ),
            first_financial_period=year_end.first_financial_period,
        )
        await record_size_assessment(
            session, org_id=auth.org_id, year_end=year_end, assessment=assessment
        )
    except SizeEligibilityRejected as exc:
        raise HTTPException(status_code=400, detail=exc.detail) from exc
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _size_response(year_end)


@router.get(
    "/{year_end_id}/size-eligibility",
    response_model=SizeEligibilityResponse,
)
async def get_size_eligibility(
    year_end_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SizeEligibilityResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    return _size_response(year_end)


@router.get(
    "/{year_end_id}/drafts/{draft_id}/dashboard",
    response_model=DashboardResponse,
)
async def get_draft_dashboard(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_reader)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DashboardResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        board = await dashboard_for_draft(
            session, org_id=auth.org_id, year_end=year_end, draft_id=draft_id
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return _dashboard_response(board)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/adjustments",
    response_model=AdjustmentPostResponse,
)
async def post_draft_adjustment(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: AdjustmentPostRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> AdjustmentPostResponse:
    key = _idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        posted = await post_adjustment(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
            narration=body.narration,
            lines=[
                PostedLine(
                    nominal_code=line.nominal_code,
                    account_name=line.account_name,
                    canonical_line=line.canonical_line,
                    debit=_pence(line.debit),
                    credit=_pence(line.credit),
                )
                for line in body.lines
            ],
            idempotency_key=key,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return AdjustmentPostResponse.model_validate(posted)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/disclosures",
    response_model=DisclosureAnswerResponse,
)
async def post_draft_disclosure(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DisclosureAnswerRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DisclosureAnswerResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        saved = await set_disclosure_answer(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
            flag_name=body.flag_name,
            answer=body.answer,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return DisclosureAnswerResponse.model_validate(saved)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/lock",
    response_model=DraftStatusResponse,
)
async def post_draft_lock(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftMutationRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DraftStatusResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        locked = await lock_draft(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return DraftStatusResponse.model_validate(locked)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/recompute",
    response_model=DashboardResponse,
)
async def post_draft_recompute(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftMutationRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> DashboardResponse:
    key = _idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        board = await recompute_draft(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
            idempotency_key=key,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return _dashboard_response(board)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/finalise",
    response_model=FinaliseResponse,
)
async def post_draft_finalise(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftMutationRequest,
    auth: Annotated[AuthContext, Depends(require_client_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> FinaliseResponse:
    key = _idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        stored = await finalise_draft(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
            user_id=auth.user_id,
            idempotency_key=key,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return FinaliseResponse.model_validate(stored)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/new-version",
    response_model=NewDraftVersionResponse,
)
async def post_draft_new_version(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftMutationRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NewDraftVersionResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        created = await new_version_from_locked(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return NewDraftVersionResponse.model_validate(created)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/acknowledge-mappings",
    response_model=DraftStatusResponse,
)
async def post_acknowledge_mappings(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftMutationRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DraftStatusResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        stored = await acknowledge_mappings(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return DraftStatusResponse.model_validate(stored)


@router.post(
    "/{year_end_id}/drafts/{draft_id}/new-report",
    response_model=NewDraftVersionResponse,
)
async def post_new_report(
    year_end_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftMutationRequest,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NewDraftVersionResponse:
    """Start an empty statutory report and freeze the previous adopted draft."""
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    try:
        created = await start_new_report(
            session,
            org_id=auth.org_id,
            year_end=year_end,
            draft_id=draft_id,
            row_version=body.row_version,
        )
    except DraftRejected as exc:
        raise _draft_error(exc) from exc
    return NewDraftVersionResponse.model_validate(created)


def _job_response(job: RenderJob) -> RenderJobResponse:
    return RenderJobResponse.model_validate(
        {
            "job_id": job.id,
            "status": job.status,
            "error_message": job.error_message,
        }
    )


async def _docx_watermark(
    *,
    year_end: YearEnd,
    version: TrialBalanceVersion,
    auth: AuthContext,
    session: AsyncSession,
) -> tuple[bool, str]:
    frozen = await frozen_snapshot(
        session, org_id=auth.org_id, tb_version_id=version.id
    )
    if frozen is not None:
        statement = frozen.get("statement")
        if not isinstance(statement, dict):
            raise HTTPException(status_code=500, detail="FINAL snapshot is missing")
        parsed = StatementResponse.model_validate(statement)
        return parsed.renderable, "FINAL"
    try:
        document = await statements_for_version(
            session, org_id=auth.org_id, year_end=year_end, version=version
        )
    except ReconciliationRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return document.renderable, document.watermark


@router.post(
    "/{year_end_id}/trial-balance-versions/{version_id}/statements.docx",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=RenderJobResponse,
)
async def post_statement_docx(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    idempotency_key: Annotated[str | None, Header()] = None,
) -> RenderJobResponse:
    key = _idempotency_key(idempotency_key)
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    existing = await find_docx_job(session, org_id=auth.org_id, idempotency_key=key)
    if existing is not None:
        if existing.tb_version_id != version.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Idempotency-Key was already used for a different "
                    "trial balance version"
                ),
            )
        return _job_response(existing)
    renderable, watermark = await _docx_watermark(
        year_end=year_end, version=version, auth=auth, session=session
    )
    if not renderable:
        raise HTTPException(
            status_code=400,
            detail="Statutory statements are not renderable",
        )
    try:
        job = await insert_docx_job(
            session,
            org_id=year_end.org_id,
            company_id=year_end.company_id,
            tb_version_id=version.id,
            idempotency_key=key,
            watermark=watermark,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Idempotency-Key was already used for a different "
                "trial balance version"
            ),
        ) from exc
    return _job_response(job)


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/render-jobs/{job_id}",
    response_model=RenderJobResponse,
)
async def get_render_job(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    job_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RenderJobResponse:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    job = await job_for_version(
        session,
        org_id=auth.org_id,
        tb_version_id=version.id,
        job_id=job_id,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="DOCX job not found")
    return _job_response(job)


@router.get(
    "/{year_end_id}/trial-balance-versions/{version_id}/render-jobs/{job_id}/download",
)
async def download_render_job(
    year_end_id: uuid.UUID,
    version_id: uuid.UUID,
    job_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[SourceObjectStorage, Depends(get_source_storage)],
) -> Response:
    await aset_rls_org_id(session, auth.org_id)
    year_end = await _owned_year_end(
        session, year_end_id=year_end_id, org_id=auth.org_id
    )
    version = await _owned_tb_version(
        session, year_end=year_end, version_id=version_id, org_id=auth.org_id
    )
    job = await job_for_version(
        session,
        org_id=auth.org_id,
        tb_version_id=version.id,
        job_id=job_id,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="DOCX job not found")
    if job.status != "ready" or job.storage_key is None:
        raise HTTPException(status_code=409, detail="DOCX is not ready")
    filename = (
        "statutory-statements-final.docx"
        if job.watermark == "FINAL"
        else "statutory-statements-draft.docx"
    )
    body = storage.get(key=job.storage_key)
    return Response(
        content=body,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
