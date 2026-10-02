"""Year ends, immutable trial-balance versions, and the prior-year gate.

Parsing runs in the worker (`tb_import_worker`), not in this request handler.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import (
    AuthContext,
    get_db_session,
    require_member_work,
    require_reader,
)
from app.models.source_document import SourceDocument
from app.models.tb_version import TrialBalanceVersion
from app.schemas.year_end import (
    PriorYearConfirmRequest,
    PriorYearLineOut,
    PriorYearResponse,
    ReconciliationGateResponse,
    TrialBalanceVersionCreate,
    TrialBalanceVersionResponse,
    YearEndCreateRequest,
    YearEndResponse,
    amount_text,
)
from app.services.ownership import get_owned_company
from app.services.prior_year import (
    PriorYearRejected,
    confirm_prior_year,
    mark_first_financial_period,
    reconciliation_gate,
)
from findraft.engine.pack import load_manifest, pack_dir, pin_pack_version
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

router = APIRouter(prefix="/year-ends", tags=["year-ends"])


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
    version: TrialBalanceVersion, draft_number: int | None
) -> TrialBalanceVersionResponse:
    return TrialBalanceVersionResponse(
        id=version.id,
        year_end_id=version.year_end_id,
        version_number=version.version_number,
        source_document_id=version.source_document_id,
        status=version.status,
        error_message=version.error_message,
        draft_version_number=draft_number,
    )


async def _draft_number(session: AsyncSession, version_id: uuid.UUID) -> int | None:
    return (
        await session.execute(
            select(DraftVersion.version_number).where(
                DraftVersion.tb_version_id == version_id
            )
        )
    ).scalar_one_or_none()


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
            return _version_response(
                existing, await _draft_number(session, existing.id)
            )
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
    return _version_response(version, None)


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
    return _version_response(version, await _draft_number(session, version.id))


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
