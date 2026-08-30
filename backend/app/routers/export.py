"""Export API — POST /trial-balances/{id}/export, GET /exports/{id}[/download] (§10.2).

Watermarking / subscription_tier is loaded from the organisations row via the
TB's client's org_id. Request-body tier or watermark flags are explicitly
stripped and never passed to the exporter (same defence pattern as
Organisations billing-field exclusion).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SyncSessionLocal, aset_rls_org_id, set_rls_org_id
from app.dependencies import AuthContext, get_auth_context, get_db_session
from app.models.client import Client
from app.models.export import Export
from app.models.financial_statement import FinancialStatement
from app.models.trial_balance import TrialBalance
from app.routers.trial_balances import _get_owned_tb
from app.schemas.export import (
    TIER_FIELDS_NOT_FROM_REQUEST,
    ExportAcceptedResponse,
    ExportCreateRequest,
    ExportOptions,
    ExportStatusResponse,
)
from app.services.export_job import (
    _load_export_context,
    default_object_storage,
    run_export_job_task,
)
from app.services.exporter import ObjectStorage, regenerate_export_if_missing

trial_balances_router = APIRouter(prefix="/trial-balances", tags=["exports"])
exports_router = APIRouter(prefix="/exports", tags=["exports"])


def get_object_storage() -> ObjectStorage:
    """Overridable in tests (in-memory stub) — production uses S3/R2."""
    return default_object_storage()


async def _get_owned_export(
    session: AsyncSession,
    *,
    export_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Export:
    result = await session.execute(
        select(Export)
        .join(TrialBalance, TrialBalance.id == Export.tb_id)
        .join(Client, Client.id == TrialBalance.client_id)
        .where(
            Export.id == export_id,
            Client.org_id == org_id,
            Client.is_deleted.is_(False),
        )
    )
    export = result.scalar_one_or_none()
    if export is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return export


@trial_balances_router.post(
    "/{tb_id}/export",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ExportAcceptedResponse,
)
async def create_export(
    tb_id: uuid.UUID,
    body: ExportCreateRequest,
    background_tasks: BackgroundTasks,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> ExportAcceptedResponse:
    await aset_rls_org_id(session, auth.org_id)
    tb = await _get_owned_tb(session, tb_id=tb_id, org_id=auth.org_id)

    # Confirm statements exist before queuing (fail fast).
    statements = await session.execute(
        select(FinancialStatement.id).where(FinancialStatement.tb_id == tb.id)
    )
    if not list(statements.scalars().all()):
        raise HTTPException(
            status_code=400,
            detail="Statements must be generated before export",
        )

    # Strip spoofable tier/watermark fields — org tier comes from DB in the job.
    raw = body.model_dump(exclude_unset=True)
    for forbidden in TIER_FIELDS_NOT_FROM_REQUEST:
        raw.pop(forbidden, None)
    options = ExportOptions.model_validate(raw.get("options") or {})

    export = Export(
        tb_id=tb.id,
        format=body.format,
        status="pending",
        options=options.model_dump(mode="json"),
    )
    session.add(export)
    await session.flush()
    # Commit before BackgroundTasks so the worker session can see the row.
    await session.commit()

    background_tasks.add_task(
        run_export_job_task,
        export_id=export.id,
        org_id=auth.org_id,
        storage=storage,
    )

    return ExportAcceptedResponse(
        export_id=export.id,
        tb_id=tb.id,
        status="pending",
        message="Export accepted. Processing will begin shortly.",
    )


@exports_router.get("/{export_id}", response_model=ExportStatusResponse)
async def get_export_status(
    export_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Export:
    await aset_rls_org_id(session, auth.org_id)
    return await _get_owned_export(session, export_id=export_id, org_id=auth.org_id)


@exports_router.get("/{export_id}/download")
async def download_export(
    export_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> RedirectResponse:
    await aset_rls_org_id(session, auth.org_id)
    export = await _get_owned_export(session, export_id=export_id, org_id=auth.org_id)

    if export.status != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Export is not ready for download (status={export.status})",
        )

    # Regeneration path uses DB-loaded org tier again — never request body.
    with SyncSessionLocal() as sync_session:
        set_rls_org_id(sync_session, auth.org_id)
        sync_export = sync_session.get(Export, export.id)
        assert sync_export is not None
        branding, package, organisation = _load_export_context(
            sync_session, export=sync_export, org_id=auth.org_id
        )
        try:
            url = regenerate_export_if_missing(
                sync_export,
                format=sync_export.format,  # type: ignore[arg-type]
                branding=branding,
                package=package,
                organisation=organisation,
                storage=storage,
                export_id=sync_export.id,
            )
        except RuntimeError as exc:
            sync_session.commit()
            raise HTTPException(
                status_code=500,
                detail=str(exc) or "Export regeneration failed",
            ) from exc
        sync_session.commit()

    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
