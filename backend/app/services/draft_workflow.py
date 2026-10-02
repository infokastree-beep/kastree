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
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import aset_rls_org_id
from app.services.draft_inputs import (
    DraftInputError,
    adjusted_for_draft,
    disclosure_flags,
    latest_draft,
)
from app.services.reconciliation import (
    ReconciliationCheck,
    ReconciliationRejected,
    load_confirmed_inputs,
)
from app.services.statutory_evidence import evidence_for_version
from app.services.statutory_present import evidence_response, statement_response
from app.services.statutory_statements import (
    StatutoryStatements,
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


def engine_sha() -> str:
    """Hash of the pure engine sources. FINAL records this and does not rerun."""
    engine = Path(__file__).resolve().parents[3] / "findraft" / "engine"
    paths = sorted(engine.glob("*.py"))
    if not paths:
        raise DraftRejected("engine sources are missing")
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


def _can_finalise(traffic: Traffic, *, renderable: bool, blocked: bool) -> bool:
    return traffic != "red" and renderable and not blocked


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


async def _disclosure_check(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft: DraftVersion,
) -> ReconciliationCheck | None:
    if draft.tb_version_id is None:
        raise DraftRejected("Draft has no trial balance")
    from app.models.tb_version import TrialBalanceVersion

    version = await session.get(TrialBalanceVersion, draft.tb_version_id)
    if version is None or version.org_id != org_id:
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
        )
    if draft.tb_version_id is None:
        raise DraftRejected("Draft has no trial balance")
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
    light = _traffic(
        tuple(checks), blocked=document.blocked, renderable=document.renderable
    )
    return Dashboard(
        draft_id=draft.id,
        status=draft.status,
        row_version=draft.row_version,
        traffic=light,
        can_finalise=_can_finalise(
            light, renderable=document.renderable, blocked=document.blocked
        ),
        checks=tuple(checks),
        unanswered_disclosures=unanswered,
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
    if draft.tb_version_id is None:
        raise DraftRejected("Draft has no trial balance")
    from app.models.tb_version import TrialBalanceVersion

    version = await session.get(TrialBalanceVersion, draft.tb_version_id)
    if version is None or version.org_id != org_id or version.status != "ready":
        raise DraftRejected("Trial balance version is not ready")
    try:
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
    draft.row_version = row_version + 1
    draft.updated_at = datetime.now(UTC)
    await session.flush()
    return {
        "draft_id": str(draft.id),
        "row_version": draft.row_version,
        "flag_name": flag_name,
        "answer": answer,
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


async def recompute_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    idempotency_key: str,
) -> Dashboard:
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


async def finalise_draft(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    year_end: YearEnd,
    draft_id: uuid.UUID,
    row_version: int,
    user_id: uuid.UUID,
    idempotency_key: str,
) -> dict[str, object]:
    request_sha = _sha({"row_version": row_version, "action": "finalise"})
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
    if draft.tb_version_id is None:
        raise DraftRejected("Draft has no trial balance")
    from app.models.tb_version import TrialBalanceVersion

    version = await session.get(TrialBalanceVersion, draft.tb_version_id)
    if version is None or version.org_id != org_id or version.status != "ready":
        raise DraftRejected("Trial balance version is not ready")
    document = await statements_for_version(
        session,
        org_id=org_id,
        year_end=year_end,
        version=version,
        watermark="FINAL",
        use_draft=draft,
    )
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
    light = _traffic(
        tuple(checks), blocked=document.blocked, renderable=document.renderable
    )
    if not _can_finalise(
        light, renderable=document.renderable, blocked=document.blocked
    ):
        detail = disc.message if disc is not None else "critical checks block FINAL"
        raise DraftRejected(detail, 409)
    graph = await evidence_for_version(
        session,
        org_id=org_id,
        year_end=year_end,
        version=version,
        use_draft=draft,
    )
    if not graph.renderable:
        raise DraftRejected(graph.build_error or "evidence graph does not tie", 409)
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
        )
    ).model_dump(mode="json")
    evidence = evidence_response(graph).model_dump(mode="json")
    inputs = await _inputs_sha(
        session, org_id=org_id, year_end=year_end, draft=draft, version_id=version.id
    )
    digest = engine_sha()
    draft.status = "final"
    draft.snapshot = {
        "watermark": "FINAL",
        "html": document.html or "",
        "statement": statement,
        "evidence": evidence,
        "traffic": light,
    }
    draft.inputs_sha256 = inputs
    draft.engine_sha = digest
    draft.finalised_by_user_id = user_id
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
    return {
        "draft_id": str(board.draft_id),
        "status": board.status,
        "row_version": board.row_version,
        "traffic": board.traffic,
        "can_finalise": board.can_finalise,
        "unanswered_disclosures": list(board.unanswered_disclosures),
        "checks": [
            {
                "code": item.code,
                "severity": item.severity,
                "passed": item.passed,
                "message": item.message,
            }
            for item in board.checks
        ],
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
    return Dashboard(
        draft_id=uuid.UUID(str(payload["draft_id"])),
        status=str(payload["status"]),
        row_version=int(str(payload["row_version"])),
        traffic=light,
        can_finalise=bool(payload.get("can_finalise")),
        checks=tuple(checks),
        unanswered_disclosures=names,
    )


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
