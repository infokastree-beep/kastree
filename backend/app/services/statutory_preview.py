"""One printed section, cut from the same HTML the PDF uses."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import aset_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.company import Company
from app.models.prior_year_line import PriorYearLine
from app.services.adopted_trial_balance import (
    active_adopted_draft,
    current_mapping_fingerprint,
)
from app.services.statutory_compose import (
    PreviewChild,
    children_of,
    compose_year_end_parts,
    extract_section_html,
    preview_document,
)
from app.services.statutory_statements import statements_for_adopted
from findraft.engine.pack import pack_dir
from findraft.models.year_end import YearEnd

NOT_RENDERABLE = "Statutory statements are not renderable"
SECTION_ABSENT = "Section is not in this draft"


class PreviewRejected(Exception):
    def __init__(self, detail: str, status_code: int) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass(frozen=True)
class SectionPreview:
    section_id: str
    anchor: str
    row_version: int
    preview_revision: str
    watermark: str
    html: str
    section_html: str
    children: tuple[PreviewChild, ...]


def pack_content_hash(pack_id: str, version: str) -> str:
    """Hash of every file in the pinned pack directory."""
    directory = pack_dir(pack_id, version)
    digest = hashlib.sha256()
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    for path in files:
        digest.update(path.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _json_ready(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError(f"preview revision cannot encode {type(value).__name__}")


def revision_token(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, separators=(",", ":"), sort_keys=True, default=_json_ready
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _letterhead_payload(company: Company) -> dict[str, object]:
    incorporated = (
        "" if company.incorporated_on is None else company.incorporated_on.isoformat()
    )
    return {
        "advisers": company.advisers or [],
        "business_address": company.business_address or "",
        "company_number": company.company_number or "",
        "directors": company.directors or [],
        "functional_currency": company.functional_currency,
        "incorporated_on": incorporated,
        "name": company.name,
        "registered_office": company.registered_office or "",
        "secretary": company.secretary or "",
        "share_classes": company.share_classes or [],
    }


async def preview_revision_payload(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    company: Company,
) -> dict[str, object]:
    """Everything that can change the printed section without a new engine."""
    await aset_rls_org_id(session, org_id)
    draft = await active_adopted_draft(session, org_id=org_id, year_end=year_end)
    fingerprint = await current_mapping_fingerprint(
        session, org_id=org_id, year_end=year_end
    )
    mappings = (
        await session.scalars(
            select(AccountMapping)
            .where(AccountMapping.company_id == year_end.company_id)
            .order_by(AccountMapping.source_code, AccountMapping.source_name)
        )
    ).all()
    prior = (
        await session.scalars(
            select(PriorYearLine)
            .where(
                PriorYearLine.org_id == org_id,
                PriorYearLine.year_end_id == year_end.id,
            )
            .order_by(PriorYearLine.canonical_line)
        )
    ).all()
    signing = year_end.signing_directors or []
    return {
        "adopted_trial_balance_id": (
            ""
            if year_end.adopted_trial_balance_id is None
            else str(year_end.adopted_trial_balance_id)
        ),
        "approval_date": (
            "" if year_end.approval_date is None else year_end.approval_date.isoformat()
        ),
        "first_financial_period": year_end.first_financial_period,
        "git_sha": settings.resolved_git_sha(),
        "letterhead": _letterhead_payload(company),
        "mapping_fingerprint": fingerprint,
        "pack_content_hash": pack_content_hash(
            year_end.pack_id, year_end.pack_version
        ),
        "pack_id": year_end.pack_id,
        "pack_version": year_end.pack_version,
        "period_end": year_end.period_end.isoformat(),
        "period_start": (
            "" if year_end.period_start is None else year_end.period_start.isoformat()
        ),
        "prior_year_lines": [
            {"amount": str(line.amount), "canonical_line": line.canonical_line}
            for line in prior
        ],
        "report_setup": year_end.report_setup,
        "row_version": 0 if draft is None else draft.row_version,
        "signing_directors": list(signing),
        "subline_choices": [
            {
                "account_name": mapping.source_name,
                "nominal_code": mapping.source_code or "",
                "statutory_line": mapping.statutory_line or "",
            }
            for mapping in mappings
        ],
    }


async def build_section_preview(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    company: Company,
    section_id: str,
) -> SectionPreview:
    payload = await preview_revision_payload(
        session, org_id=org_id, year_end=year_end, company=company
    )
    document = await statements_for_adopted(
        session, org_id=org_id, year_end=year_end
    )
    if not document.renderable or document.html is None:
        raise PreviewRejected(NOT_RENDERABLE, 400)
    full_html, sections = compose_year_end_parts(document, year_end, company=company)
    section_html = extract_section_html(full_html, section_id)
    if section_html is None:
        raise PreviewRejected(SECTION_ABSENT, 404)
    row_version = payload["row_version"]
    assert isinstance(row_version, int)
    return SectionPreview(
        section_id=section_id,
        anchor=section_id,
        row_version=row_version,
        preview_revision=revision_token(payload),
        watermark=document.watermark,
        html=preview_document(full_html, section_html),
        section_html=section_html,
        children=children_of(sections, section_id),
    )
