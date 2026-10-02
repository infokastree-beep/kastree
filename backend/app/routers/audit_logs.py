"""Practice audit log. The CSV is an export. The policy is readable by every role."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.dependencies import (
    AuthContext,
    get_db_session,
    require_member_work,
    require_reader,
)
from app.schemas.audit import AuditChainResponse, RetentionPolicyResponse
from app.services.audit import load_audit_log, render_audit_csv, verify_audit_chain
from app.services.retention import (
    RETAINED_ON_ERASURE,
    RETENTION_POLICY_STATEMENT,
    RETENTION_YEARS,
    STATUTORY_FLOOR_YEARS,
)

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("/policy", response_model=RetentionPolicyResponse)
async def get_retention_policy(
    auth: Annotated[AuthContext, Depends(require_reader)],
) -> RetentionPolicyResponse:
    del auth
    return RetentionPolicyResponse(
        statutory_floor_years=STATUTORY_FLOOR_YEARS,
        retention_years=RETENTION_YEARS,
        buffer_is_statutory=False,
        erasure_replaces=["user email", "user login identifier", "client name"],
        erasure_retains=list(RETAINED_ON_ERASURE),
        statement=RETENTION_POLICY_STATEMENT,
    )


@router.get("", response_model=AuditChainResponse)
async def get_audit_chain(
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuditChainResponse:
    await aset_rls_org_id(session, auth.org_id)
    rows = await load_audit_log(session, org_id=auth.org_id)
    return AuditChainResponse(count=len(rows), chain_valid=verify_audit_chain(rows))


@router.get("/export.csv")
async def export_audit_csv(
    auth: Annotated[AuthContext, Depends(require_member_work)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    await aset_rls_org_id(session, auth.org_id)
    rows = await load_audit_log(session, org_id=auth.org_id)
    valid = verify_audit_chain(rows)
    return Response(
        content=render_audit_csv(rows),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="audit-log.csv"',
            "X-Audit-Chain-Valid": "true" if valid else "false",
        },
    )
