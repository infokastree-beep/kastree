"""Week 10 draft workflow: adjustments, disclosure answers, lock, and FINAL.

FINAL writes one snapshot and is never recomputed. A reviewer (owner or
admin) is the only role that may finalise; the router enforces that.
"""

from __future__ import annotations

import ast
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.models.company import Company
from app.models.organisation import Organisation
from app.services.audit import append_audit_log
from app.services.beta import final_page_presentation
from app.services.disclosure_groups import (
    DisclosureQuestion,
    present_disclosure_questions,
)
from app.services.note_library import (
    LibraryRejected,
    LibraryRow,
    apply_library_action,
    parse_note_library,
    present_rows,
    to_storage,
)
from app.services.draft_inputs import (
    DraftInputError,
    adjusted_for_draft,
    disclosure_flags,
    latest_draft,
)
from app.services.reconciliation import (
    ConfirmedInputs,
    ReconciliationCheck,
    ReconciliationRejected,
    load_confirmed_inputs,
)
from app.services.render_jobs import payload_from_composed
from app.services.statutory_evidence import evidence_for_adopted, evidence_for_version
from app.services.statutory_present import evidence_response, statement_response
from app.services.adopted_trial_balance import (
    current_mapping_fingerprint,
    freeze_payload,
    inputs_for_adopted_draft,
    load_adopted_inputs,
)
from app.services.statutory_compose import (
    compose_year_end_parts,
    docx_presentation_for_year_end,
    pack_display_notices,
    unbuilt_section_notices,
)
from app.services.statutory_statements import (
    StatutoryStatements,
    canonical_current,
    statements_for_adopted,
    statements_for_version,
)
from findraft.engine.mapping import aggregate
from findraft.engine.notes import (
    ANSWER_FLAGS,
    DERIVED,
    build_note_context,
    check_disclosure_answers,
)
from findraft.engine.pack import pack_dir
from findraft.models.adjustments import (
    AdjustmentJournal,
    AdjustmentLine,
    DisclosureAnswer,
    DraftOperation,
)
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd

Traffic = Literal["red", "amber", "green"]


class DraftRejected(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass(frozen=True)
class PostedLine:
    nominal_code: str
    account_name: str
    canonical_line: str
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class Dashboard:
    draft_id: uuid.UUID
    status: str
    row_version: int
    traffic: Traffic
    can_finalise: bool
    checks: tuple[ReconciliationCheck, ...]
    unanswered_disclosures: tuple[str, ...]
    carried_disclosures: tuple[str, ...]
    disclosure_questions: tuple[DisclosureQuestion, ...] = ()


ENGINE_FILES_MISSING = (
    "The accounts calculation files are missing from the server. "
    "Finalise cannot run until the application is updated."
)


def engine_directory(start: Path | None = None) -> Path | None:
    """Directory that holds the pure engine modules.

    The repository keeps that directory beside ``backend``. The production
    image copies ``backend`` onto ``/app`` and the engine to
    ``/app/findraft/engine``. Counting a fixed number of parents from this
    file then looks above the image and finds nothing, even though the
    modules were copied and can be imported.
    """
    origin = Path(__file__).resolve() if start is None else start
    for parent in origin.parents:
        candidate = parent / "findraft" / "engine"
        if any(candidate.glob("*.py")):
            return candidate
    return None


def engine_files_missing_message(year_end_id: uuid.UUID) -> str:
    """Plain sentence. The two links are pages that do not hold the files."""
    trial = f"/year-ends/{year_end_id}/draft?section=trial-balance"
    company = f"/year-ends/{year_end_id}/draft?section=company-details"
    return (
        f"{ENGINE_FILES_MISSING} "
        f"Check the [Trial balance page]({trial}) and "
        f"[Company details]({company}); they do not hold these files."
    )


def engine_sha() -> str:
    """Hash of the pure engine sources. FINAL records this and does not rerun."""
    engine = engine_directory()
    if engine is None:
        raise DraftRejected(ENGINE_FILES_MISSING)
    paths = sorted(engine.glob("*.py"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _templates(directory: Path) -> dict[str, dict[str, object]]:
    templates: dict[str, dict[str, object]] = {}
    for path in sorted((directory / "notes").glob("*.json")):
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            templates[path.stem] = loaded
    return templates


def _checklist(directory: Path) -> list[dict[str, object]]:
    loaded = json.loads(
        (directory / "disclosure-checklist.json").read_text(encoding="utf-8")
    )
    items = loaded.get("items") if isinstance(loaded, dict) else None
    if not isinstance(items, list):
        raise DraftRejected("disclosure checklist is missing")
    return [item for item in items if isinstance(item, dict)]


def _unanswered(message: str) -> tuple[str, ...]:
    prefix = "Unanswered disclosure questions: "
    if not message.startswith(prefix):
        return ()
    parsed = ast.literal_eval(message[len(prefix) :])
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed)


def _stored_traffic(value: object, *, default: Traffic) -> Traffic:
    if value == "red":
        return "red"
    if value == "amber":
        return "amber"
    if value == "green":
        return "green"
    return default


def _traffic(
    checks: tuple[ReconciliationCheck, ...],
    *,
    blocked: bool,
    renderable: bool,
) -> Traffic:
    failed = [item for item in checks if not item.passed]
    if blocked or any(item.severity in {"CRITICAL", "BLOCKED"} for item in failed):
        return "red"
    if not renderable or failed:
        return "amber" if failed and renderable else "red"
    return "green"


def _can_finalise(
    traffic: Traffic,
    *,
    renderable: bool,
    blocked: bool,
    checks: tuple[ReconciliationCheck, ...] = (),
) -> bool:
    from app.services.company_details import blocks_final

    return traffic != "red" and renderable and not blocked and not blocks_final(checks)


async def _draft_for_update(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
) -> DraftVersion:
    await aset_rls_org_id(session, org_id)
    draft = (
        await session.scalars(
            select(DraftVersion)
            .where(
                DraftVersion.id == draft_id,
                DraftVersion.org_id == org_id,
                DraftVersion.year_end_id == year_end.id,
            )
            .with_for_update()
        )
    ).first()
    if draft is None:
        raise DraftRejected("Draft not found", 404)
    return draft


def _expect_version(draft: DraftVersion, row_version: int) -> None:
    if draft.row_version != row_version:
        raise DraftRejected("row_version does not match", 409)


def _refuse_frozen(draft: DraftVersion) -> None:
    if draft.is_frozen:
        raise DraftRejected("draft is frozen; writes are refused", 409)


def closed_draft_message(draft: DraftVersion) -> str | None:
    """Final, locked, and frozen drafts do not take a further change."""
    if draft.status == "final":
        return "This draft is final. It cannot be changed."
    if draft.status == "locked":
        return "This draft is locked. It cannot be changed."
    if draft.is_frozen:
        return "This draft is frozen. It cannot be changed."
    return None


def audit_position_write_refusal(draft: DraftVersion) -> str | None:
    """Size inputs, the claim, and the confirmations stay as finalised.

    A later draft version is the working copy. The latest draft is the one
    that decides. Final, locked, and frozen each refuse the write.
    """
    if draft.status == "final":
        return "This draft is final. The audit position cannot be changed."
    if draft.status == "locked":
        return "This draft is locked. The audit position cannot be changed."
    if draft.is_frozen:
        return "This draft is frozen. The audit position cannot be changed."
    return None


def present_status(
    *, status: str, can_finalise: bool, blocking_count: int
) -> dict[str, str | None]:
    """One lifecycle. Readiness exists only while the draft is not final."""
    if status == "final":
        return {"lifecycle": "Final", "readiness": None}
    if can_finalise:
        readiness = "Ready to finalise"
    elif blocking_count == 1:
        readiness = "1 blocker"
    else:
        readiness = f"{blocking_count} blockers"
    return {"lifecycle": "Draft", "readiness": readiness}


async def _replay(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    key: str,
    request_sha: str,
) -> dict[str, object] | None:
    await aset_rls_org_id(session, org_id)
    row = await session.scalar(
        select(DraftOperation).where(
            DraftOperation.org_id == org_id,
            DraftOperation.idempotency_key == key,
        )
    )
    if row is None:
        return None
    if row.request_sha256 != request_sha:
        raise DraftRejected(
            "Idempotency-Key was already used for a different request", 409
        )
    return row.response


async def _remember(
    session: AsyncSession,
    *,
    draft: DraftVersion,
    action: str,
    key: str,
    request_sha: str,
    response: dict[str, object],
) -> None:
    session.add(
        DraftOperation(
            org_id=draft.org_id,
            company_id=draft.company_id,
            draft_version_id=draft.id,
            action=action,
            idempotency_key=key,
            request_sha256=request_sha,
            response=response,
        )
    )
    await session.flush()


async def _loaded_for_check(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
) -> ConfirmedInputs:
    if draft.tb_version_id is None:
        return await inputs_for_adopted_draft(
            session, org_id=org_id, year_end=year_end, draft=draft
        )
    from app.models.tb_version import TrialBalanceVersion

    version = await session.get(TrialBalanceVersion, draft.tb_version_id)
    if version is None or version.org_id != org_id:
        raise DraftRejected("Trial balance version is not ready")
    return await load_confirmed_inputs(
        session, org_id=org_id, year_end=year_end, version=version
    )


async def _disclosure_check(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
) -> ReconciliationCheck | None:
    try:
        loaded = await _loaded_for_check(
            session, org_id=org_id, year_end=year_end, draft=draft
        )
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    adjusted = await adjusted_for_draft(
        session,
        org_id=org_id,
        draft=draft,
        tb_lines=loaded.tb_lines,
        mappings=loaded.mappings,
    )
    directory = pack_dir(year_end.pack_id, year_end.pack_version)
    templates = _templates(directory)
    aggregated = aggregate(adjusted.tb_lines, adjusted.mappings)
    context = build_note_context(aggregated, templates, adjusted.flags)
    result = check_disclosure_answers(context, templates, _checklist(directory))
    if result is None:
        return None
    return ReconciliationCheck(
        code=result.code,
        severity=result.severity,
        passed=result.passed,
        message=result.message,
    )


def _company_detail_checks(
    company: Company,
    year_end: YearEnd,
    document: StatutoryStatements,
    flags: dict[str, bool],
    *,
    practice_name: str,
    practice_address: str,
    practice_contact: str,
) -> tuple[ReconciliationCheck, ...]:
    from app.services.company_details import company_detail_checks

    return company_detail_checks(
        company,
        year_end,
        turnover=document.turnover,
        profit_before_tax=document.profit_before_tax,
        tax_charge=document.tax_charge,
        corporation_tax=document.corporation_tax,
        subsequent_events_answered="SUBSEQUENT_EVENTS" in flags,
        own_shares_held=(
            flags["OWN_SHARES_HELD"] if "OWN_SHARES_HELD" in flags else None
        ),
        subsequent_events_yes=(
            flags["SUBSEQUENT_EVENTS"] if "SUBSEQUENT_EVENTS" in flags else None
        ),
        practice_name=practice_name,
        practice_address=practice_address,
        practice_contact=practice_contact,
        disclosure_flags=flags,
    )


def _letterhead_from(organisation: object | None) -> tuple[str, str, str]:
    if organisation is None:
        return "", "", ""
    name = getattr(organisation, "name", None)
    address = getattr(organisation, "letterhead_address", None)
    contact = getattr(organisation, "letterhead_contact", None)
    return (
        "" if name is None else str(name),
        "" if address is None else str(address),
        "" if contact is None else str(contact),
    )


async def dashboard_for_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
) -> Dashboard:
    await aset_rls_org_id(session, org_id)
    draft = await session.get(DraftVersion, draft_id)
    if draft is None or draft.org_id != org_id or draft.year_end_id != year_end.id:
        raise DraftRejected("Draft not found", 404)
    flags = await disclosure_flags(session, org_id=org_id, draft_id=draft.id)
    questions = present_disclosure_questions(flags)
    if draft.status == "final" and isinstance(draft.snapshot, dict):
        stored_checks = draft.snapshot.get("statement")
        checks: list[ReconciliationCheck] = []
        if isinstance(stored_checks, dict):
            raw_checks = stored_checks.get("checks")
            if isinstance(raw_checks, list):
                for item in raw_checks:
                    if isinstance(item, dict):
                        checks.append(
                            ReconciliationCheck(
                                code=str(item.get("code")),
                                severity=str(item.get("severity")),
                                passed=bool(item.get("passed")),
                                message=str(item.get("message")),
                            )
                        )
        light = _stored_traffic(draft.snapshot.get("traffic"), default="green")
        return Dashboard(
            draft_id=draft.id,
            status=draft.status,
            row_version=draft.row_version,
            traffic=light,
            can_finalise=False,
            checks=tuple(checks),
            unanswered_disclosures=(),
            carried_disclosures=(),
            disclosure_questions=questions,
        )
    try:
        if draft.tb_version_id is None:
            document = await statements_for_adopted(
                session,
                org_id=org_id,
                year_end=year_end,
                use_draft=draft,
            )
        else:
            from app.models.tb_version import TrialBalanceVersion

            version = await session.get(TrialBalanceVersion, draft.tb_version_id)
            if version is None or version.org_id != org_id:
                raise DraftRejected("Trial balance version is not ready")
            document = await statements_for_version(
                session,
                org_id=org_id,
                year_end=year_end,
                version=version,
                use_draft=draft,
            )
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    disc = await _disclosure_check(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    checks = list(document.checks)
    unanswered: tuple[str, ...] = ()
    if disc is None:
        checks.append(
            ReconciliationCheck(
                code="V-DISC-001",
                severity="PASS",
                passed=True,
                message="Disclosure questions are answered",
            )
        )
    else:
        checks.append(disc)
        unanswered = _unanswered(disc.message)
    company = await session.scalar(
        select(Company).where(
            Company.id == year_end.company_id,
            Company.org_id == org_id,
        )
    )
    currency = "GBP"
    if company is not None and not company.is_deleted:
        practice_name, practice_address, practice_contact = _letterhead_from(
            await session.get(Organisation, org_id)
        )
        checks.extend(
            _company_detail_checks(
                company,
                year_end,
                document,
                flags,
                practice_name=practice_name,
                practice_address=practice_address,
                practice_contact=practice_contact,
            )
        )
        currency = company.functional_currency or "GBP"
    checks.extend(unbuilt_section_notices(year_end))
    checks.extend(pack_display_notices(year_end, currency))
    light = _traffic(
        tuple(checks), blocked=document.blocked, renderable=document.renderable
    )
    carried = await _carried_disclosure_names(session, org_id=org_id, draft=draft)
    return Dashboard(
        draft_id=draft.id,
        status=draft.status,
        row_version=draft.row_version,
        traffic=light,
        can_finalise=_can_finalise(
            light,
            renderable=document.renderable,
            blocked=document.blocked,
            checks=tuple(checks),
        ),
        checks=tuple(checks),
        unanswered_disclosures=unanswered,
        carried_disclosures=tuple(sorted(carried)),
        disclosure_questions=questions,
    )


def _validate_journal(lines: list[PostedLine], narration: str) -> str:
    text = narration.strip()
    if not text or len(text) > 500:
        raise DraftRejected("narration is required")
    if len(lines) < 2:
        raise DraftRejected("an adjustment journal needs at least two lines")
    debit = Decimal("0")
    credit = Decimal("0")
    for line in lines:
        if line.debit < 0 or line.credit < 0:
            raise DraftRejected("amounts must be non-negative")
        one_side = (line.debit > 0 and line.credit == 0) or (
            line.credit > 0 and line.debit == 0
        )
        if not one_side:
            raise DraftRejected("each adjustment line has one side")
        if not line.nominal_code.strip() or not line.account_name.strip():
            raise DraftRejected("each adjustment line needs a code and a name")
        debit += line.debit
        credit += line.credit
    if debit != credit:
        raise DraftRejected("adjustment journal does not balance")
    return text


async def post_adjustment(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    narration: str,
    lines: list[PostedLine],
    idempotency_key: str,
) -> dict[str, object]:
    request_sha = _sha(
        {
            "narration": narration,
            "lines": [
                (
                    line.nominal_code,
                    line.account_name,
                    line.canonical_line,
                    str(line.debit),
                    str(line.credit),
                )
                for line in lines
            ],
            "row_version": row_version,
        }
    )
    replay = await _replay(
        session, org_id=org_id, key=idempotency_key, request_sha=request_sha
    )
    if replay is not None:
        return replay
    text = _validate_journal(lines, narration)
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status != "draft":
        raise DraftRejected(f"draft is {draft.status}; writes are refused", 409)
    _refuse_frozen(draft)
    journal = AdjustmentJournal(
        org_id=draft.org_id,
        company_id=draft.company_id,
        draft_version_id=draft.id,
        narration=text,
    )
    session.add(journal)
    await session.flush()
    for index, line in enumerate(lines, start=1):
        session.add(
            AdjustmentLine(
                org_id=draft.org_id,
                company_id=draft.company_id,
                journal_id=journal.id,
                draft_version_id=draft.id,
                line_no=index,
                nominal_code=line.nominal_code.strip(),
                account_name=line.account_name.strip(),
                canonical_line=line.canonical_line.strip(),
                debit=line.debit,
                credit=line.credit,
            )
        )
    await session.flush()
    try:
        if draft.tb_version_id is None:
            loaded = await inputs_for_adopted_draft(
                session, org_id=org_id, year_end=year_end, draft=draft
            )
        else:
            from app.models.tb_version import TrialBalanceVersion

            version = await session.get(TrialBalanceVersion, draft.tb_version_id)
            if version is None or version.org_id != org_id or version.status != "ready":
                raise DraftRejected("Trial balance version is not ready")
            loaded = await load_confirmed_inputs(
                session, org_id=org_id, year_end=year_end, version=version
            )
        await adjusted_for_draft(
            session,
            org_id=org_id,
            draft=draft,
            tb_lines=loaded.tb_lines,
            mappings=loaded.mappings,
        )
    except DraftInputError as exc:
        raise DraftRejected(exc.detail) from exc
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    response: dict[str, object] = {
        "journal_id": str(journal.id),
        "draft_id": str(draft.id),
        "row_version": draft.row_version,
        "line_count": len(lines),
    }
    await _remember(
        session,
        draft=draft,
        action="adjust",
        key=idempotency_key,
        request_sha=request_sha,
        response=response,
    )
    return response


async def set_disclosure_answer(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    flag_name: str,
    answer: Literal["yes", "no", "unanswered"],
) -> dict[str, object]:
    if flag_name in DERIVED or flag_name not in ANSWER_FLAGS:
        raise DraftRejected("unknown disclosure answer name")
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status != "draft":
        raise DraftRejected(f"draft is {draft.status}; writes are refused", 409)
    _refuse_frozen(draft)
    existing = await session.scalar(
        select(DisclosureAnswer).where(
            DisclosureAnswer.org_id == org_id,
            DisclosureAnswer.draft_version_id == draft.id,
            DisclosureAnswer.flag_name == flag_name,
        )
    )
    if answer == "unanswered":
        if existing is not None:
            await session.delete(existing)
    elif existing is None:
        session.add(
            DisclosureAnswer(
                org_id=draft.org_id,
                company_id=draft.company_id,
                draft_version_id=draft.id,
                flag_name=flag_name,
                answer=answer == "yes",
            )
        )
    else:
        existing.answer = answer == "yes"
        existing.updated_at = datetime.now(UTC)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="disclosure_answered",
        entity_type="draft_version",
        entity_id=draft.id,
        new_value={"flag_name": flag_name, "answer": answer},
    )
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    return {
        "draft_id": str(draft.id),
        "row_version": draft.row_version,
        "flag_name": flag_name,
        "answer": answer,
    }


_LIBRARY_AUDIT: dict[str, str] = {
    "omit": "note_block_omitted",
    "restore": "note_block_restored",
    "add": "note_block_added",
    "remove": "note_block_add_removed",
}


def _copied_library(raw: object) -> dict[str, object] | None:
    if raw is None:
        return None
    try:
        stored = to_storage(parse_note_library(raw))
    except LibraryRejected as exc:
        raise DraftRejected("note library is unreadable") from exc
    if stored is None:
        return None
    copied = _json_copy(stored)
    if not isinstance(copied, dict):
        raise DraftRejected("note library is unreadable")
    return {str(key): value for key, value in copied.items()}


def _library_row_payload(row: LibraryRow) -> dict[str, object]:
    return {
        "block_id": row.block_id,
        "title": row.title,
        "reason": row.reason,
        "sentence": row.sentence,
        "can_omit": row.can_omit,
        "can_restore": row.can_restore,
        "can_add": row.can_add,
        "can_remove": row.can_remove,
        "kind": row.kind,
        "note_class": row.note_class,
        "note_class_label": row.note_class_label,
    }


async def _library_context(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
) -> dict[str, object]:
    try:
        loaded = await _loaded_for_check(
            session, org_id=org_id, year_end=year_end, draft=draft
        )
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    adjusted = await adjusted_for_draft(
        session,
        org_id=org_id,
        draft=draft,
        tb_lines=loaded.tb_lines,
        mappings=loaded.mappings,
    )
    directory = pack_dir(year_end.pack_id, year_end.pack_version)
    context = build_note_context(
        aggregate(adjusted.tb_lines, adjusted.mappings),
        _templates(directory),
        adjusted.flags,
    )
    if not isinstance(context, dict):
        raise DraftRejected("note context is missing")
    return {str(key): value for key, value in context.items()}


async def notes_for_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
) -> dict[str, object]:
    """Library rows for this draft. Reading does not create a row."""
    await aset_rls_org_id(session, org_id)
    draft = await session.get(DraftVersion, draft_id)
    if draft is None or draft.org_id != org_id or draft.year_end_id != year_end.id:
        raise DraftRejected("Draft not found", 404)
    library_source: object = draft.note_library
    if draft.status == "final" and isinstance(draft.snapshot, dict):
        if "note_library" in draft.snapshot:
            library_source = draft.snapshot.get("note_library")
    try:
        library = parse_note_library(library_source)
    except LibraryRejected as exc:
        raise DraftRejected(exc.detail) from exc
    rows = present_rows(
        await _library_context(session, org_id=org_id, year_end=year_end, draft=draft),
        library,
    )
    return {
        "draft_id": str(draft.id),
        "row_version": draft.row_version,
        "rows": [_library_row_payload(row) for row in rows],
    }


async def set_note_block(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    block_id: str,
    action: Literal["omit", "restore", "add", "remove"],
) -> dict[str, object]:
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status != "draft":
        raise DraftRejected(f"draft is {draft.status}; writes are refused", 409)
    _refuse_frozen(draft)
    context = await _library_context(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    try:
        updated = apply_library_action(
            parse_note_library(draft.note_library),
            block_id=block_id,
            action=action,
            ctx=context,
        )
    except LibraryRejected as exc:
        raise DraftRejected(exc.detail, 422) from exc
    draft.note_library = to_storage(updated)
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action=_LIBRARY_AUDIT[action],
        entity_type="draft_version",
        entity_id=draft.id,
        new_value={"block_id": block_id},
    )
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    return {
        "draft_id": str(draft.id),
        "row_version": draft.row_version,
        "block_id": block_id,
        "action": action,
    }


async def mark_remaining_disclosures_no(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    confirm: bool,
) -> dict[str, object]:
    """Write No for flags that are unanswered now. Already answered flags stay as they are."""
    if confirm is not True:
        raise DraftRejected("confirmation is required", 422)
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status != "draft":
        raise DraftRejected(f"draft is {draft.status}; writes are refused", 409)
    _refuse_frozen(draft)
    current = await disclosure_flags(session, org_id=org_id, draft_id=draft.id)
    pending = sorted(
        name for name in ANSWER_FLAGS if name not in current and name not in DERIVED
    )
    if not pending:
        raise DraftRejected("no disclosure questions are unanswered", 422)
    for name in pending:
        session.add(
            DisclosureAnswer(
                org_id=draft.org_id,
                company_id=draft.company_id,
                draft_version_id=draft.id,
                flag_name=name,
                answer=False,
            )
        )
    await append_audit_log(
        session,
        org_id=org_id,
        user_id=user_id,
        action="disclosures_marked_remaining_no",
        entity_type="draft_version",
        entity_id=draft.id,
        new_value={"count": len(pending), "flag_ids": pending},
    )
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    return {
        "draft_id": str(draft.id),
        "row_version": draft.row_version,
        "count": len(pending),
        "flag_ids": pending,
    }


async def lock_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
) -> dict[str, object]:
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status != "draft":
        raise DraftRejected(f"draft is {draft.status}; writes are refused", 409)
    _refuse_frozen(draft)
    draft.status = "locked"
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    return {
        "draft_id": str(draft.id),
        "status": draft.status,
        "row_version": draft.row_version,
    }


async def new_version_from_locked(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
) -> dict[str, object]:
    await aset_rls_org_id(session, org_id)
    await session.scalars(
        select(YearEnd)
        .where(YearEnd.id == year_end.id, YearEnd.org_id == org_id)
        .with_for_update()
    )
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status != "locked":
        raise DraftRejected("a new version starts from a locked draft", 409)
    current = (
        await session.scalar(
            select(func.max(DraftVersion.version_number)).where(
                DraftVersion.year_end_id == year_end.id
            )
        )
    ) or 0
    created = DraftVersion(
        org_id=draft.org_id,
        company_id=draft.company_id,
        year_end_id=draft.year_end_id,
        version_number=int(current) + 1,
        pack_id=draft.pack_id,
        pack_version=draft.pack_version,
        status="draft",
        tb_version_id=draft.tb_version_id,
        row_version=1,
        note_library=_copied_library(draft.note_library),
    )
    session.add(created)
    await session.flush()
    journals = (
        await session.scalars(
            select(AdjustmentJournal).where(
                AdjustmentJournal.draft_version_id == draft.id,
                AdjustmentJournal.org_id == org_id,
            )
        )
    ).all()
    for journal in journals:
        copied = AdjustmentJournal(
            org_id=created.org_id,
            company_id=created.company_id,
            draft_version_id=created.id,
            narration=journal.narration,
        )
        session.add(copied)
        await session.flush()
        source_lines = (
            await session.scalars(
                select(AdjustmentLine)
                .where(AdjustmentLine.journal_id == journal.id)
                .order_by(AdjustmentLine.line_no)
            )
        ).all()
        for line in source_lines:
            session.add(
                AdjustmentLine(
                    org_id=created.org_id,
                    company_id=created.company_id,
                    journal_id=copied.id,
                    draft_version_id=created.id,
                    line_no=line.line_no,
                    nominal_code=line.nominal_code,
                    account_name=line.account_name,
                    canonical_line=line.canonical_line,
                    debit=line.debit,
                    credit=line.credit,
                )
            )
    flags = await disclosure_flags(session, org_id=org_id, draft_id=draft.id)
    for name, value in flags.items():
        session.add(
            DisclosureAnswer(
                org_id=created.org_id,
                company_id=created.company_id,
                draft_version_id=created.id,
                flag_name=name,
                answer=value,
            )
        )
    await session.flush()
    return {
        "draft_id": str(created.id),
        "version_number": created.version_number,
        "row_version": created.row_version,
        "status": created.status,
    }


async def acknowledge_mappings(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
) -> dict[str, object]:
    """Store the live Product 1 mapping fingerprint on this draft."""
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.tb_version_id is not None:
        raise DraftRejected("This draft does not read Product 1 mappings", 409)
    if draft.status == "final":
        raise DraftRejected("FINAL output is never recomputed", 409)
    refusal = closed_draft_message(draft)
    if refusal is not None:
        raise DraftRejected(refusal, 409)
    try:
        fingerprint = await current_mapping_fingerprint(
            session, org_id=org_id, year_end=year_end
        )
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    draft.mappings_sha256 = fingerprint
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    return {
        "draft_id": str(draft.id),
        "status": draft.status,
        "row_version": draft.row_version,
    }


async def start_new_report(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
) -> dict[str, object]:
    """Open an empty adopted draft and freeze the one it replaces.

    Journals and disclosure answers stay on the previous draft. This path
    does not call ``new_version_from_locked``.
    """
    await aset_rls_org_id(session, org_id)
    await session.scalars(
        select(YearEnd)
        .where(YearEnd.id == year_end.id, YearEnd.org_id == org_id)
        .with_for_update()
    )
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.tb_version_id is not None or year_end.adopted_trial_balance_id is None:
        raise DraftRejected("A new statutory report starts from the adopted draft", 409)
    if draft.status == "final":
        raise DraftRejected("FINAL output is never recomputed", 409)
    if draft.status == "locked":
        raise DraftRejected("This draft is locked. It cannot be changed.", 409)
    current = (
        await session.scalar(
            select(func.max(DraftVersion.version_number)).where(
                DraftVersion.year_end_id == year_end.id
            )
        )
    ) or 0
    if draft.is_frozen or draft.version_number != int(current):
        raise DraftRejected("This draft is not the active report", 409)
    try:
        loaded = await load_adopted_inputs(session, org_id=org_id, year_end=year_end)
        fingerprint = await current_mapping_fingerprint(
            session, org_id=org_id, year_end=year_end
        )
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    created = DraftVersion(
        org_id=draft.org_id,
        company_id=draft.company_id,
        year_end_id=draft.year_end_id,
        version_number=int(current) + 1,
        pack_id=draft.pack_id,
        pack_version=draft.pack_version,
        status="draft",
        tb_version_id=None,
        mappings_sha256=fingerprint,
        is_frozen=False,
        row_version=1,
    )
    try:
        async with session.begin_nested():
            draft.is_frozen = True
            draft.frozen_inputs = freeze_payload(loaded)
            draft.row_version = row_version + 1
            draft.updated_at = datetime.now(UTC)
            session.add(created)
            await session.flush()
    except IntegrityError as exc:
        raise DraftRejected("A report for this year end was just started", 409) from exc
    return {
        "draft_id": str(created.id),
        "version_number": created.version_number,
        "row_version": created.row_version,
        "status": created.status,
    }


async def recompute_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    idempotency_key: str,
) -> Dashboard:
    """Recompute through the dashboard.

    An adopted draft reads ``load_adopted_inputs`` there. A frozen draft
    reads the snapshot stored when the next report started.
    """
    request_sha = _sha({"row_version": row_version, "action": "recompute"})
    replay = await _replay(
        session, org_id=org_id, key=idempotency_key, request_sha=request_sha
    )
    if replay is not None:
        return _dashboard_from_response(replay)
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status == "final":
        raise DraftRejected("FINAL output is never recomputed", 409)
    refusal = closed_draft_message(draft)
    if refusal is not None:
        raise DraftRejected(refusal, 409)
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    board = await dashboard_for_draft(
        session, org_id=org_id, year_end=year_end, draft_id=draft.id
    )
    response = _dashboard_dict(board)
    await _remember(
        session,
        draft=draft,
        action="recompute",
        key=idempotency_key,
        request_sha=request_sha,
        response=response,
    )
    return board


def _json_copy(value: object) -> object:
    try:
        copied: object = json.loads(json.dumps(value))
    except (TypeError, ValueError) as exc:
        raise DraftRejected("composed snapshot is unreadable") from exc
    return copied


async def _carried_disclosure_names(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    draft: DraftVersion,
) -> frozenset[str]:
    """Flag names copied forward by ``new_version_from_locked``.

    That path is the only one that copies answers, and it starts from a
    locked draft. A new report leaves the previous draft unfrozen of that
    copy, so its status stays draft and nothing here is carried over.
    """
    if draft.version_number < 2:
        return frozenset()
    previous = await session.scalar(
        select(DraftVersion).where(
            DraftVersion.org_id == org_id,
            DraftVersion.year_end_id == draft.year_end_id,
            DraftVersion.version_number == draft.version_number - 1,
        )
    )
    if previous is None or previous.status != "locked":
        return frozenset()
    current = await disclosure_flags(session, org_id=org_id, draft_id=draft.id)
    parent = await disclosure_flags(session, org_id=org_id, draft_id=previous.id)
    return frozenset(set(current) & set(parent))


async def _adopted_inputs_sha(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
) -> str:
    loaded = await _loaded_for_check(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    adjusted = await adjusted_for_draft(
        session,
        org_id=org_id,
        draft=draft,
        tb_lines=loaded.tb_lines,
        mappings=loaded.mappings,
    )
    adopted_id = year_end.adopted_trial_balance_id
    return _sha(
        {
            "adopted_trial_balance_id": None if adopted_id is None else str(adopted_id),
            "frozen": draft.is_frozen,
            "pack_id": year_end.pack_id,
            "pack_version": year_end.pack_version,
            "mappings": sorted(adjusted.mappings.items()),
            "lines": [
                (
                    line.nominal_code,
                    line.account_name,
                    str(line.debit),
                    str(line.credit),
                )
                for line in adjusted.tb_lines
            ],
            "flags": sorted(adjusted.flags.items()),
            "prior": sorted(
                (key, str(value)) for key, value in loaded.prior_canonical.items()
            ),
        }
    )


async def finalise_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    user_id: uuid.UUID,
    idempotency_key: str,
    reviewed_carried_disclosures: bool = False,
) -> dict[str, object]:
    request_sha = _sha(
        {
            "row_version": row_version,
            "action": "finalise",
            "reviewed_carried_disclosures": reviewed_carried_disclosures,
        }
    )
    replay = await _replay(
        session, org_id=org_id, key=idempotency_key, request_sha=request_sha
    )
    if replay is not None:
        return replay
    draft = await _draft_for_update(
        session, org_id=org_id, year_end=year_end, draft_id=draft_id
    )
    _expect_version(draft, row_version)
    if draft.status == "final":
        raise DraftRejected("FINAL output is never recomputed", 409)
    from app.services.company_details import (
        incorporation_output_message_for_year_end,
    )

    incorporation = await incorporation_output_message_for_year_end(
        session, org_id=org_id, year_end=year_end, final=True
    )
    if incorporation is not None:
        raise DraftRejected(incorporation, 409)
    adopted = draft.tb_version_id is None
    if adopted and year_end.adopted_trial_balance_id is None:
        raise DraftRejected("Draft has no trial balance")
    version_id: uuid.UUID | None = None
    try:
        if adopted:
            document = await statements_for_adopted(
                session,
                org_id=org_id,
                year_end=year_end,
                watermark="FINAL",
                use_draft=draft,
            )
        else:
            from app.models.tb_version import TrialBalanceVersion

            version = await session.get(TrialBalanceVersion, draft.tb_version_id)
            if version is None or version.org_id != org_id or version.status != "ready":
                raise DraftRejected("Trial balance version is not ready")
            version_id = version.id
            document = await statements_for_version(
                session,
                org_id=org_id,
                year_end=year_end,
                version=version,
                watermark="FINAL",
                use_draft=draft,
            )
    except ReconciliationRejected as exc:
        raise DraftRejected(exc.detail, exc.status_code) from exc
    disc = await _disclosure_check(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    checks = list(document.checks)
    if disc is not None:
        checks.append(disc)
    else:
        checks.append(
            ReconciliationCheck(
                code="V-DISC-001",
                severity="PASS",
                passed=True,
                message="Disclosure questions are answered",
            )
        )
    company = await session.get(Company, year_end.company_id)
    if company is not None and company.org_id == org_id and not company.is_deleted:
        flags = await disclosure_flags(session, org_id=org_id, draft_id=draft.id)
        practice_name, practice_address, practice_contact = _letterhead_from(
            await session.get(Organisation, org_id)
        )
        checks.extend(
            _company_detail_checks(
                company,
                year_end,
                document,
                flags,
                practice_name=practice_name,
                practice_address=practice_address,
                practice_contact=practice_contact,
            )
        )
    light = _traffic(
        tuple(checks), blocked=document.blocked, renderable=document.renderable
    )
    if not _can_finalise(
        light,
        renderable=document.renderable,
        blocked=document.blocked,
        checks=tuple(checks),
    ):
        from app.services.company_details import blocks_final

        blocking = next(
            (
                item.message
                for item in checks
                if not item.passed and blocks_final((item,))
            ),
            None,
        )
        detail = blocking or (
            disc.message if disc is not None else "critical checks block FINAL"
        )
        raise DraftRejected(detail, 409)
    if adopted:
        graph = await evidence_for_adopted(
            session,
            org_id=org_id,
            year_end=year_end,
            use_draft=draft,
        )
    else:
        from app.models.tb_version import TrialBalanceVersion

        if version_id is None:
            raise DraftRejected("Trial balance version is not ready")
        version = await session.get(TrialBalanceVersion, version_id)
        if version is None or version.org_id != org_id:
            raise DraftRejected("Trial balance version is not ready")
        graph = await evidence_for_version(
            session,
            org_id=org_id,
            year_end=year_end,
            version=version,
            use_draft=draft,
        )
    if not graph.renderable:
        raise DraftRejected(graph.build_error or "evidence graph does not tie", 409)
    carried = await _carried_disclosure_names(session, org_id=org_id, draft=draft)
    if carried and not reviewed_carried_disclosures:
        raise DraftRejected(
            "Carried-over disclosure answers have not been acknowledged.",
            409,
        )
    statement = statement_response(
        StatutoryStatements(
            watermark=document.watermark,
            renderable=document.renderable,
            blocked=document.blocked,
            build_error=document.build_error,
            checks=tuple(checks),
            net_assets=document.net_assets,
            profit=document.profit,
            compliance_statement=document.compliance_statement,
            sofp=document.sofp,
            income=document.income,
            notes=document.notes,
            rounding_flags=document.rounding_flags,
            html=document.html,
            pages=document.pages,
            company_name=document.company_name,
            turnover=document.turnover,
            balance_sheet_total=document.balance_sheet_total,
        )
    ).model_dump(mode="json")
    evidence = evidence_response(graph).model_dump(mode="json")
    loaded = await _loaded_for_check(
        session, org_id=org_id, year_end=year_end, draft=draft
    )
    adjusted = await adjusted_for_draft(
        session,
        org_id=org_id,
        draft=draft,
        tb_lines=loaded.tb_lines,
        mappings=loaded.mappings,
    )
    if adopted:
        inputs = await _adopted_inputs_sha(
            session, org_id=org_id, year_end=year_end, draft=draft
        )
    elif version_id is not None:
        inputs = await _inputs_sha(
            session,
            org_id=org_id,
            year_end=year_end,
            draft=draft,
            version_id=version_id,
        )
    else:
        raise DraftRejected("Trial balance version is not ready")
    letterhead = (
        company
        if company is not None and company.org_id == org_id and not company.is_deleted
        else None
    )
    try:
        composed_html, sections = compose_year_end_parts(
            document,
            year_end,
            company=letterhead,
            disclosure_flags=adjusted.flags,
        )
        page_header, signature = docx_presentation_for_year_end(document, year_end)
        composed_docx = payload_from_composed(
            watermark=document.watermark,
            company_name=document.company_name,
            sections=sections,
            page_header=page_header,
            signature=signature,
        )
        current = canonical_current(adjusted.tb_lines, adjusted.mappings)
    except ValueError as exc:
        raise DraftRejected(str(exc), 409) from exc
    copied_sections = _json_copy(sections)
    copied_docx = _json_copy(composed_docx)
    if not isinstance(copied_sections, list) or not isinstance(copied_docx, dict):
        raise DraftRejected("composed snapshot is unreadable")
    try:
        digest = engine_sha()
    except DraftRejected as exc:
        if exc.detail == ENGINE_FILES_MISSING:
            raise DraftRejected(engine_files_missing_message(year_end.id)) from exc
        raise
    draft.inputs_sha256 = inputs
    draft.engine_sha = digest
    draft.finalised_by_user_id = user_id
    draft.status = "final"
    presentation = final_page_presentation(document.watermark)
    from app.services.final_workspace import workspace_snapshot

    draft.snapshot = {
        "watermark": "FINAL",
        "wording_signed_off": presentation.wording_signed_off,
        "page_label": presentation.page_label,
        "wording_banner": presentation.wording_banner,
        "html": document.html or "",
        "composed_html": composed_html,
        "composed_sections": copied_sections,
        "composed_docx": copied_docx,
        "canonical_current": {
            key: str(amount) for key, amount in sorted(current.items())
        },
        "statement": statement,
        "evidence": evidence,
        "traffic": light,
        "note_library": _copied_library(draft.note_library),
        "workspace": workspace_snapshot(year_end, letterhead),
    }
    if carried:
        await append_audit_log(
            session,
            org_id=org_id,
            user_id=user_id,
            action="carried_disclosures_reviewed",
            entity_type="draft_version",
            entity_id=draft.id,
            new_value={"reviewed": True, "flag_names": sorted(carried)},
        )
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    response: dict[str, object] = {
        "draft_id": str(draft.id),
        "status": "final",
        "row_version": draft.row_version,
        "inputs_sha256": inputs,
        "engine_sha": digest,
        "pack_id": draft.pack_id,
        "pack_version": draft.pack_version,
        "traffic": light,
    }
    await _remember(
        session,
        draft=draft,
        action="finalise",
        key=idempotency_key,
        request_sha=request_sha,
        response=response,
    )
    await session.flush()
    return response


async def _inputs_sha(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
    version_id: uuid.UUID,
) -> str:
    from app.models.tb_version import TrialBalanceVersion

    version = await session.get(TrialBalanceVersion, version_id)
    if version is None:
        raise DraftRejected("Trial balance version is not ready")
    loaded = await load_confirmed_inputs(
        session, org_id=org_id, year_end=year_end, version=version
    )
    adjusted = await adjusted_for_draft(
        session,
        org_id=org_id,
        draft=draft,
        tb_lines=loaded.tb_lines,
        mappings=loaded.mappings,
    )
    return _sha(
        {
            "tb_version_id": str(version_id),
            "pack_id": year_end.pack_id,
            "pack_version": year_end.pack_version,
            "mappings": sorted(adjusted.mappings.items()),
            "lines": [
                (
                    line.nominal_code,
                    line.account_name,
                    str(line.debit),
                    str(line.credit),
                )
                for line in adjusted.tb_lines
            ],
            "flags": sorted(adjusted.flags.items()),
            "prior": sorted(
                (key, str(value)) for key, value in loaded.prior_canonical.items()
            ),
        }
    )


def _dashboard_dict(board: Dashboard) -> dict[str, object]:
    from app.services.dashboard_groups import blocking_failure_count, present_check

    checks: list[dict[str, object]] = []
    for item in board.checks:
        shown = present_check(item.code)
        checks.append(
            {
                "code": item.code,
                "severity": item.severity,
                "passed": item.passed,
                "message": item.message,
                "area": shown.area,
                "fix": {
                    "section": shown.fix.section,
                    "note": shown.fix.note,
                    "anchor": shown.fix.anchor,
                },
            }
        )
    blocking_count = blocking_failure_count(board.checks)
    return {
        "draft_id": str(board.draft_id),
        "status": board.status,
        "row_version": board.row_version,
        "traffic": board.traffic,
        "can_finalise": board.can_finalise,
        "status_view": present_status(
            status=board.status,
            can_finalise=board.can_finalise,
            blocking_count=blocking_count,
        ),
        "unanswered_disclosures": list(board.unanswered_disclosures),
        "unanswered_count": len(board.unanswered_disclosures),
        "blocking_count": blocking_count,
        "carried_disclosures": list(board.carried_disclosures),
        "disclosure_questions": [
            {
                "flag_name": row.flag_name,
                "question": row.question,
                "group": row.group,
                "note": row.note,
                "answer": row.answer,
            }
            for row in board.disclosure_questions
        ],
        "checks": checks,
    }


def _dashboard_from_response(payload: dict[str, object]) -> Dashboard:
    raw_checks = payload.get("checks")
    checks: list[ReconciliationCheck] = []
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if isinstance(item, dict):
                checks.append(
                    ReconciliationCheck(
                        code=str(item.get("code")),
                        severity=str(item.get("severity")),
                        passed=bool(item.get("passed")),
                        message=str(item.get("message")),
                    )
                )
    light = _stored_traffic(payload.get("traffic"), default="red")
    unanswered = payload.get("unanswered_disclosures")
    names = (
        tuple(str(item) for item in unanswered) if isinstance(unanswered, list) else ()
    )
    raw_carried = payload.get("carried_disclosures")
    carried = (
        tuple(str(item) for item in raw_carried)
        if isinstance(raw_carried, list)
        else ()
    )
    questions = _disclosure_questions_from_payload(payload.get("disclosure_questions"))
    return Dashboard(
        draft_id=uuid.UUID(str(payload["draft_id"])),
        status=str(payload["status"]),
        row_version=int(str(payload["row_version"])),
        traffic=light,
        can_finalise=bool(payload.get("can_finalise")),
        checks=tuple(checks),
        unanswered_disclosures=names,
        carried_disclosures=carried,
        disclosure_questions=questions,
    )


def _stored_answer(value: object) -> Literal["yes", "no", "unanswered"] | None:
    if value == "yes":
        return "yes"
    if value == "no":
        return "no"
    if value == "unanswered":
        return "unanswered"
    return None


def _disclosure_questions_from_payload(raw: object) -> tuple[DisclosureQuestion, ...]:
    if not isinstance(raw, list):
        return ()
    rows: list[DisclosureQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        answer = _stored_answer(item.get("answer"))
        if answer is None:
            continue
        note = item.get("note")
        rows.append(
            DisclosureQuestion(
                flag_name=str(item.get("flag_name") or ""),
                question=str(item.get("question") or ""),
                group=str(item.get("group") or ""),
                note=note if isinstance(note, str) else None,
                answer=answer,
            )
        )
    return tuple(rows)


async def frozen_snapshot(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    tb_version_id: uuid.UUID,
) -> dict[str, object] | None:
    draft = await latest_draft(session, org_id=org_id, tb_version_id=tb_version_id)
    if draft is None:
        return None
    return draft.snapshot if draft.status == "final" else None
