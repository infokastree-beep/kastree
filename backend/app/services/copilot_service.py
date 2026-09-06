"""Copilot orchestration: load evidence → LLM → ground → audit.

No UI. Callers (API router or live scripts) supply an RLS-scoped session and
auth identity. Cross-company context is impossible: loaders resolve the TB
through the org join and tools only read that company/TB's artifacts.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from openai import OpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.copilot_turn import CopilotTurn
from app.models.processing_job import ProcessingJob
from app.schemas.copilot import (
    CopilotAnswer,
    EvidencePack,
    GroundedCopilotAnswer,
)
from app.services.copilot_evidence import build_evidence_pack
from app.services.copilot_grounding import ground_answer
from app.services.copilot_llm import generate_copilot_answer
from app.services.copilot_loaders import (
    load_commentaries,
    load_owned_copilot_context,
    load_performance_periods,
    load_risk_flags,
    load_variance_items,
)
from app.services.rate_limit import enforce_rate_limit_key

logger = logging.getLogger(__name__)

COPILOT_MAX_REQUESTS_PER_USER_PER_HOUR = 30


@dataclass(frozen=True, slots=True)
class CopilotAskResult:
    pack: EvidencePack
    raw_answer: CopilotAnswer
    grounded: GroundedCopilotAnswer
    model_used: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    turn_id: uuid.UUID
    processing_job_id: uuid.UUID


async def ask_copilot(
    session: AsyncSession,
    *,
    tb_id: uuid.UUID,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    question: str,
    openai_client: OpenAI | None = None,
) -> CopilotAskResult:
    """Full Copilot turn under the caller's org RLS session."""
    enforce_rate_limit_key(
        key=f"copilot:{org_id}:{user_id}",
        max_requests=COPILOT_MAX_REQUESTS_PER_USER_PER_HOUR,
        window=timedelta(hours=1),
    )

    ctx = await load_owned_copilot_context(session, tb_id=tb_id, org_id=org_id)
    tb = ctx.tb
    company = ctx.company

    job = ProcessingJob(
        tb_id=tb.id,
        job_type="copilot",
        status="running",
        step="load_evidence",
        progress_pct=10,
        attempt_count=1,
        started_at=datetime.now(timezone.utc),
    )
    session.add(job)
    await session.flush()

    try:
        periods = await load_performance_periods(
            session,
            company_id=company.id,
            as_of=tb.period_end,
            current_tb_id=tb.id,
        )
        variance_items = await load_variance_items(session, tb_id=tb.id)
        commentaries = await load_commentaries(session, tb_id=tb.id)
        risk_flags = await load_risk_flags(session, tb_id=tb.id)

        job.step = "build_pack"
        job.progress_pct = 40

        currency = (tb.currency or company.functional_currency or "GBP").upper()
        pack = build_evidence_pack(
            question=question,
            company_id=company.id,
            company_name=company.name,
            tb_id=tb.id,
            period_end=tb.period_end,
            currency=currency,
            prior_period_end=ctx.prior_period_end,
            periods=periods,
            variance_items=variance_items,
            risk_flags=risk_flags,
            commentaries=commentaries,
            health=None,
        )

        job.step = "llm"
        job.progress_pct = 60
        llm_result = generate_copilot_answer(
            question=question,
            pack=pack,
            openai_client=openai_client,
        )

        job.step = "ground"
        job.progress_pct = 85
        grounded = ground_answer(llm_result.answer, pack)

        job.prompt_tokens = llm_result.prompt_tokens
        job.completion_tokens = llm_result.completion_tokens
        job.total_tokens = llm_result.total_tokens
        job.model_used = llm_result.model_used
        job.status = "complete"
        job.step = "done"
        job.progress_pct = 100
        job.completed_at = datetime.now(timezone.utc)

        turn = CopilotTurn(
            tb_id=tb.id,
            user_id=user_id,
            org_id=org_id,
            question=question,
            intent=pack.intent.value,
            evidence_pack=pack.model_dump(mode="json"),
            raw_answer=llm_result.answer.model_dump(mode="json"),
            grounded_answer=grounded.model_dump(mode="json"),
            model_used=llm_result.model_used,
            prompt_tokens=llm_result.prompt_tokens,
            completion_tokens=llm_result.completion_tokens,
            total_tokens=llm_result.total_tokens,
            processing_job_id=job.id,
        )
        session.add(turn)
        await session.flush()

        return CopilotAskResult(
            pack=pack,
            raw_answer=llm_result.answer,
            grounded=grounded,
            model_used=llm_result.model_used,
            prompt_tokens=llm_result.prompt_tokens,
            completion_tokens=llm_result.completion_tokens,
            total_tokens=llm_result.total_tokens,
            turn_id=turn.id,
            processing_job_id=job.id,
        )
    except Exception as exc:
        logger.exception("Copilot ask failed for tb_id=%s", tb_id)
        job.status = "failed"
        job.error_message = str(exc)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        await session.flush()
        raise
