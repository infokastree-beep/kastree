"""Background parse → map pipeline for trial balance uploads (MVP BackgroundTasks)."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.account_mapping import AccountMapping
from app.models.processing_job import ProcessingJob
from app.models.trial_balance import TrialBalance
from app.services.mapper import (
    MappingResult,
    SleepFn,
    map_accounts_for_client,
)
from app.services.parser import TBRow, parse_tb_file

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tb_row_to_dict(row: TBRow) -> dict[str, Any]:
    return {
        "account_code": row.account_code,
        "account_name": row.account_name,
        "debit": str(row.debit),
        "credit": str(row.credit),
        "net_balance": str(row.net_balance),
        "currency": row.currency,
        "row_index": row.row_index,
    }


def run_parse_and_map_job(
    *,
    tb_id: uuid.UUID,
    org_id: uuid.UUID,
    parse_job_id: uuid.UUID,
    map_job_id: uuid.UUID,
    openai_client: Any | None = None,
    sleep: SleepFn = time.sleep,
) -> None:
    """Parse the uploaded file then run mapper tiers 1–4; update jobs + TB status."""
    with SyncSessionLocal() as session:
        try:
            set_rls_org_id(session, org_id)
            tb = session.get(TrialBalance, tb_id)
            parse_job = session.get(ProcessingJob, parse_job_id)
            map_job = session.get(ProcessingJob, map_job_id)
            if tb is None or parse_job is None or map_job is None:
                logger.error("Missing TB/jobs for parse/map tb_id=%s", tb_id)
                return

            # --- parse ---
            tb.status = "parsing"
            parse_job.status = "running"
            parse_job.started_at = _utcnow()
            parse_job.step = "Parsing trial balance file"
            parse_job.progress_pct = 10
            session.commit()

            set_rls_org_id(session, org_id)
            path = Path(tb.file_url.removeprefix("file://"))
            file_bytes = path.read_bytes()
            rows = parse_tb_file(
                file_bytes,
                filename=path.name,
                functional_currency=tb.currency or "GBP",
            )
            tb.parsed_data = {"rows": [_tb_row_to_dict(row) for row in rows]}
            tb.raw_data = {"filename": path.name, "size_bytes": tb.file_size_bytes}
            parse_job.status = "complete"
            parse_job.progress_pct = 100
            parse_job.completed_at = _utcnow()
            session.commit()

            # --- map ---
            set_rls_org_id(session, org_id)
            tb.status = "mapping"
            map_job.status = "running"
            map_job.started_at = _utcnow()
            map_job.step = "Mapping accounts (tiers 1–4)"
            map_job.progress_pct = 20
            session.commit()

            set_rls_org_id(session, org_id)
            # Always run Tiers 1–4. When openai_client is None, mapper constructs
            # OpenAI() from env; missing OPENAI_API_KEY correctly exhausts the
            # mini→4o retry chain and leaves method=None for persistence as llm.
            results = map_accounts_for_client(
                session,
                tb.client_id,
                rows,
                openai_client=openai_client,
                sleep=sleep,
            )
            _persist_mapping_results(session, client_id=tb.client_id, results=results)
            map_job.status = "complete"
            map_job.progress_pct = 100
            map_job.completed_at = _utcnow()
            tb.status = "mapping"
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.exception("parse/map failed for tb_id=%s", tb_id)
            with SyncSessionLocal() as err_session:
                set_rls_org_id(err_session, org_id)
                tb = err_session.get(TrialBalance, tb_id)
                parse_job = err_session.get(ProcessingJob, parse_job_id)
                map_job = err_session.get(ProcessingJob, map_job_id)
                if tb is not None:
                    tb.status = "failed"
                    tb.error_message = str(exc)
                for job in (parse_job, map_job):
                    if job is not None and job.status != "complete":
                        job.status = "failed"
                        job.error_message = str(exc)
                        job.completed_at = _utcnow()
                err_session.commit()


def _persist_mapping_results(
    session: Session,
    *,
    client_id: uuid.UUID,
    results: list[MappingResult],
) -> None:
    for result in results:
        if result.method is None:
            # Tier 4 was attempted (or returned unmapped) and did not resolve.
            # Persist as llm + unmapped — never "manual" (reserved for human confirm).
            canonical = "unmapped"
            method = "llm"
        else:
            canonical = result.canonical_line or "unmapped"
            method = result.method
        existing = session.scalar(
            select(AccountMapping).where(
                AccountMapping.client_id == client_id,
                AccountMapping.source_code == result.source_code,
                AccountMapping.source_name == result.source_name,
            )
        )
        if existing is not None:
            if existing.is_confirmed:
                continue
            existing.canonical_line = canonical
            existing.confidence = result.confidence
            existing.method = method
            continue
        session.add(
            AccountMapping(
                client_id=client_id,
                source_code=result.source_code,
                source_name=result.source_name,
                canonical_line=canonical,
                confidence=result.confidence,
                method=method,
                is_confirmed=False,
                is_ignored=False,
            )
        )


def parsed_rows_from_tb(tb: TrialBalance) -> list[TBRow]:
    payload = tb.parsed_data or {}
    rows_data = payload.get("rows") or []
    return [
        TBRow(
            account_code=str(item["account_code"]),
            account_name=str(item["account_name"]),
            debit=Decimal(str(item["debit"])),
            credit=Decimal(str(item["credit"])),
            net_balance=Decimal(str(item["net_balance"])),
            currency=str(item.get("currency") or tb.currency or "GBP"),
            row_index=int(item.get("row_index") or 0),
        )
        for item in rows_data
    ]


# silence unused import warning for asdict if any
_ = asdict
