"""Queue and render a statutory DOCX outside the request handler.

The handler inserts a pending job. ``process_render_job`` claims it with
``FOR UPDATE SKIP LOCKED`` and runs the DOCX child under a timeout. A FINAL
job reads the stored snapshot. Celery and Redis are not used.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db import AsyncSessionLocal, SyncSessionLocal, aset_rls_org_id, set_rls_org_id
from app.models.tb_version import TrialBalanceVersion
from app.models.company import Company
from app.schemas.year_end import StatementResponse
from app.services.reconciliation import ReconciliationRejected
from app.services.report_setup import section_id_for_label, starts_new_page
from app.services.source_storage import SourceObjectStorage, practice_storage_key
from app.services.statutory_compose import compose_year_end_parts, docx_presentation
from app.services.statutory_statements import (
    StatutoryStatements,
    statements_for_adopted,
    statements_for_version,
)
from findraft.models.draft_version import DraftVersion
from findraft.models.render_job import RenderJob
from findraft.models.year_end import YearEnd

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RENDER_TIMEOUT_SECONDS = 20
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class RenderRejected(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _as_job(value: object) -> RenderJob | None:
    if value is None:
        return None
    if not isinstance(value, RenderJob):
        raise RenderRejected("DOCX job is missing", 500)
    return value


async def find_docx_job(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    idempotency_key: str,
) -> RenderJob | None:
    await aset_rls_org_id(session, org_id)
    found = await session.scalar(
        select(RenderJob).where(
            RenderJob.org_id == org_id,
            RenderJob.idempotency_key == idempotency_key,
        )
    )
    return _as_job(found)


async def insert_docx_job(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    company_id: uuid.UUID,
    idempotency_key: str,
    watermark: str,
    tb_version_id: uuid.UUID | None = None,
    draft_id: uuid.UUID | None = None,
) -> RenderJob:
    if tb_version_id is None and draft_id is None:
        raise RenderRejected("DOCX job has no source")
    await aset_rls_org_id(session, org_id)
    job = RenderJob(
        org_id=org_id,
        company_id=company_id,
        tb_version_id=tb_version_id,
        draft_id=draft_id,
        format="docx",
        status="pending",
        idempotency_key=idempotency_key,
        watermark=watermark,
    )
    session.add(job)
    await session.flush()
    return job


async def job_for_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    draft_id: uuid.UUID,
    job_id: uuid.UUID,
) -> RenderJob | None:
    await aset_rls_org_id(session, org_id)
    found = await session.scalar(
        select(RenderJob).where(
            RenderJob.id == job_id,
            RenderJob.org_id == org_id,
            RenderJob.draft_id == draft_id,
        )
    )
    return _as_job(found)


async def job_for_version(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    tb_version_id: uuid.UUID,
    job_id: uuid.UUID,
) -> RenderJob | None:
    await aset_rls_org_id(session, org_id)
    found = await session.scalar(
        select(RenderJob).where(
            RenderJob.id == job_id,
            RenderJob.org_id == org_id,
            RenderJob.tb_version_id == tb_version_id,
        )
    )
    return _as_job(found)


def run_docx_job(
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    storage: SourceObjectStorage,
) -> None:
    """BackgroundTasks entry. A different session sees the committed job row."""
    with SyncSessionLocal() as session:
        process_render_job(session, org_id=org_id, job_id=job_id, storage=storage)


def process_render_job(
    session: Session,
    *,
    org_id: uuid.UUID,
    job_id: uuid.UUID,
    storage: SourceObjectStorage,
) -> RenderJob | None:
    """Claim one pending DOCX job. Returns None when another worker holds it."""
    set_rls_org_id(session, org_id)
    claimed = session.execute(
        text(
            """
            SELECT id FROM findraft_render_jobs
            WHERE id = :id AND org_id = :org AND status = 'pending'
            FOR UPDATE SKIP LOCKED
            """
        ),
        {"id": str(job_id), "org": str(org_id)},
    ).scalar_one_or_none()
    if claimed is None:
        session.rollback()
        return None
    job = session.get(RenderJob, job_id)
    if job is None or job.status != "pending":
        session.rollback()
        return None
    job.status = "running"
    job.updated_at = datetime.now(UTC)
    session.commit()

    set_rls_org_id(session, org_id)
    current = session.get(RenderJob, job_id)
    if current is None:
        return None
    try:
        payload = _payload(session, current)
        body = _render_bytes(payload)
        key = practice_storage_key(
            org_id=current.org_id,
            company_id=current.company_id,
            document_id=current.id,
        )
        storage.put(key=key, body=body, content_type=DOCX_MEDIA)
        current.status = "ready"
        current.storage_key = key
        current.error_message = None
        current.updated_at = datetime.now(UTC)
        session.commit()
        return current
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        RuntimeError,
        ReconciliationRejected,
    ) as exc:
        session.rollback()
        set_rls_org_id(session, org_id)
        failed = session.get(RenderJob, job_id)
        if failed is None:
            return None
        failed.status = "failed"
        failed.error_message = _error_text(exc)
        failed.updated_at = datetime.now(UTC)
        session.commit()
        return failed


def docx_payload(document: StatutoryStatements) -> dict[str, object]:
    """JSON object the child renders. Amounts are already text."""
    from app.services.statutory_present import statement_response

    statement = statement_response(document).model_dump(mode="json")
    return payload_from_statement(statement)


def annotate_page_starts(
    payload: dict[str, object], report_setup: object
) -> dict[str, object]:
    """Copy the report-setup page-start choice onto the blocks Word writes."""
    pages = payload.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            heading = page.get("heading")
            section_id = (
                section_id_for_label(heading) if isinstance(heading, str) else None
            )
            page["new_page"] = (
                False
                if section_id is None
                else starts_new_page(section_id, report_setup)
            )
    payload["sofp_new_page"] = starts_new_page("sofp", report_setup)
    payload["income_new_page"] = starts_new_page("income", report_setup)
    payload["notes_new_page"] = starts_new_page("notes", report_setup)
    return payload


def _report_setup_for_job(session: Session, job: RenderJob) -> object:
    version = session.get(TrialBalanceVersion, job.tb_version_id)
    if version is None:
        return None
    year_end = session.get(YearEnd, version.year_end_id)
    if year_end is None or year_end.org_id != job.org_id:
        return None
    return year_end.report_setup


def payload_from_statement(statement: Mapping[str, object]) -> dict[str, object]:
    parsed = StatementResponse.model_validate(statement)
    return {
        "watermark": parsed.watermark,
        "company_name": parsed.company_name,
        "compliance_statement": parsed.compliance_statement or "",
        "pages": [
            {"heading": page.heading, "paragraphs": list(page.paragraphs)}
            for page in parsed.pages
        ],
        "sofp": [
            {
                "label": row.label,
                "current": row.current,
                "prior": "" if row.prior is None else row.prior,
            }
            for row in parsed.sofp
        ],
        "income": [
            {
                "label": row.label,
                "current": row.current,
                "prior": "" if row.prior is None else row.prior,
            }
            for row in parsed.income
        ],
        "notes": [
            {
                "code": note.code,
                "title": "" if note.title is None else note.title,
                "body": note.body,
                "lines": [
                    {"line": line.line, "current": line.current, "prior": line.prior}
                    for line in note.lines
                ],
            }
            for note in parsed.notes
        ],
    }


def payload_from_composed(
    *,
    watermark: str,
    company_name: str,
    sections: list[dict[str, object]],
    page_header: str | None = None,
    signature: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """DOCX payload built from composed sections. Amounts stay display text."""
    payload: dict[str, object] = {
        "watermark": watermark,
        "company_name": company_name,
        "page_header": page_header if page_header else watermark,
        "composed": sections,
    }
    if signature is not None:
        payload["signature"] = dict(signature)
    return payload


def _composed_payload(session: Session, job: RenderJob) -> dict[str, object]:
    draft_id = job.draft_id
    if draft_id is None:
        raise ValueError("Draft not found")
    draft = session.get(DraftVersion, draft_id)
    if draft is None or draft.org_id != job.org_id:
        raise ValueError("Draft not found")
    if draft.status == "final":
        snapshot = draft.snapshot
        stored = snapshot.get("composed_docx") if isinstance(snapshot, dict) else None
        if not isinstance(stored, dict) or stored.get("watermark") != "FINAL":
            raise ValueError("FINAL snapshot is missing")
        return {str(key): value for key, value in stored.items()}
    return _load_composed(job.org_id, draft.id)


def _load_composed(org_id: uuid.UUID, draft_id: uuid.UUID) -> dict[str, object]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            lambda: asyncio.run(_live_composed(org_id, draft_id))
        ).result()


async def _live_composed(org_id: uuid.UUID, draft_id: uuid.UUID) -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        await aset_rls_org_id(session, org_id)
        draft = await session.get(DraftVersion, draft_id)
        if draft is None or draft.org_id != org_id or draft.status == "final":
            raise RuntimeError("Draft not found")
        year_end = await session.get(YearEnd, draft.year_end_id)
        if year_end is None or year_end.org_id != org_id:
            raise RuntimeError("Year end not found")
        company = await session.get(Company, year_end.company_id)
        if company is None or company.org_id != org_id:
            raise RuntimeError("Company not found")
        if draft.tb_version_id is None:
            document = await statements_for_adopted(
                session,
                org_id=org_id,
                year_end=year_end,
                watermark="DRAFT",
                use_draft=draft,
            )
        else:
            version = await session.get(TrialBalanceVersion, draft.tb_version_id)
            if version is None or version.org_id != org_id:
                raise RuntimeError("Trial balance version is not ready")
            document = await statements_for_version(
                session,
                org_id=org_id,
                year_end=year_end,
                version=version,
                watermark="DRAFT",
                use_draft=draft,
            )
        if not document.renderable:
            raise ValueError("Statutory statements are not renderable")
        _html, sections = compose_year_end_parts(document, year_end, company=company)
        page_header, signature = docx_presentation(
            document,
            report_setup=year_end.report_setup,
            approval_date=year_end.approval_date,
            signing_directors=year_end.signing_directors,
        )
        return payload_from_composed(
            watermark=document.watermark,
            company_name=document.company_name,
            sections=sections,
            page_header=page_header,
            signature=signature,
        )


def _payload(session: Session, job: RenderJob) -> dict[str, object]:
    if job.draft_id is not None:
        return _composed_payload(session, job)
    draft = session.scalar(
        select(DraftVersion)
        .where(
            DraftVersion.org_id == job.org_id,
            DraftVersion.tb_version_id == job.tb_version_id,
        )
        .order_by(DraftVersion.version_number.desc())
        .limit(1)
    )
    if draft is not None and draft.status == "final":
        snapshot = draft.snapshot
        if not isinstance(snapshot, dict):
            raise ValueError("FINAL snapshot is missing")
        statement = snapshot.get("statement")
        if not isinstance(statement, dict):
            raise ValueError("FINAL snapshot is missing")
        return annotate_page_starts(
            payload_from_statement(statement), _report_setup_for_job(session, job)
        )
    if job.tb_version_id is None:
        raise ValueError("Trial balance version is not ready")
    document = _load_live(job.org_id, job.tb_version_id)
    if not document.renderable:
        raise ValueError("Statutory statements are not renderable")
    return annotate_page_starts(
        docx_payload(document), _report_setup_for_job(session, job)
    )


def _load_live(org_id: uuid.UUID, tb_version_id: uuid.UUID) -> StatutoryStatements:
    """Run the async statement loader on a thread so a live loop can call the worker."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            lambda: asyncio.run(_live_statements(org_id, tb_version_id))
        ).result()


async def _live_statements(
    org_id: uuid.UUID, tb_version_id: uuid.UUID
) -> StatutoryStatements:
    async with AsyncSessionLocal() as session:
        await aset_rls_org_id(session, org_id)
        version = await session.get(TrialBalanceVersion, tb_version_id)
        if version is None or version.org_id != org_id or version.status != "ready":
            raise RuntimeError("Trial balance version is not ready")
        year_end = await session.get(YearEnd, version.year_end_id)
        if year_end is None or year_end.org_id != org_id:
            raise RuntimeError("Year end not found")
        return await statements_for_version(
            session, org_id=org_id, year_end=year_end, version=version
        )


def _render_bytes(payload: Mapping[str, object]) -> bytes:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "in.json"
        dest = root / "out.docx"
        source.write_text(json.dumps(payload), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.services.docx_child",
                str(source),
                str(dest),
            ],
            cwd=_BACKEND_ROOT,
            check=True,
            timeout=RENDER_TIMEOUT_SECONDS,
            capture_output=True,
        )
        return dest.read_bytes()


def _error_text(exc: BaseException) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return "DOCX render timed out"
    if isinstance(exc, ValueError):
        detail = str(exc).strip()
        if detail in {
            "FINAL snapshot is missing",
            "Statutory statements are not renderable",
        }:
            return detail
    return "DOCX render failed"
