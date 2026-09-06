"""Live Copilot Phase-2 proof against production Berkshire data.

Runs under org RLS as the findraft role, calls the real OpenAI API, then
prints the evidence pack, raw LLM answer, and grounded answer.

Usage (env already prepared by agent):
  source /tmp/copilot_live.env && python scripts/live_copilot_berkshire.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Allow running from repo root or backend/
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import aset_rls_org_id  # noqa: E402
from app.services.copilot_service import ask_copilot  # noqa: E402

# Production Berkshire (queried earlier in this session).
ORG_ID = uuid.UUID("08bc47c2-6642-5448-b4e8-50a29527d92b")
USER_ID = uuid.UUID("fcc8c6b9-fe55-5fc0-bcb9-fd95ee933298")
TB_ID = uuid.UUID("fd2e4bf4-773c-4c7c-adbe-b3cb78dda028")
QUESTION = "What moved vs prior period for revenue and operating expenses?"


def _require_env() -> str:
    url = os.environ.get("LIVE_DATABASE_URL")
    key = os.environ.get("OPENAI_API_KEY")
    if not url or not key:
        raise SystemExit("LIVE_DATABASE_URL and OPENAI_API_KEY are required")
    return url


async def main() -> None:
    db_url = _require_env()
    engine = create_async_engine(db_url, connect_args={"ssl": "require"})
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    async with Session() as session:
        await aset_rls_org_id(session, ORG_ID)
        # Prove RLS scoping: we can see Berkshire TB and not leak existence checks.
        visible = await session.execute(
            text("SELECT id, period_end FROM trial_balances WHERE id = :tb"),
            {"tb": TB_ID},
        )
        row = visible.first()
        print("=== RLS check ===")
        print("visible TB:", row)

        result = await ask_copilot(
            session,
            tb_id=TB_ID,
            org_id=ORG_ID,
            user_id=USER_ID,
            question=QUESTION,
            openai_client=openai_client,
        )
        await session.commit()

    print("\n=== QUESTION ===")
    print(QUESTION)

    print("\n=== EVIDENCE PACK ===")
    pack_json = result.pack.model_dump(mode="json")
    # Compact but readable: intent, tools, key slices.
    summary = {
        "company_name": pack_json.get("company_name"),
        "period_end": pack_json.get("period_end"),
        "prior_period_end": pack_json.get("prior_period_end"),
        "intent": pack_json.get("intent"),
        "tools_used": pack_json.get("tools_used"),
        "refusal_reason": pack_json.get("refusal_reason"),
        "period_count": len(pack_json.get("periods") or []),
        "variance_item_count": len(pack_json.get("variance_items") or []),
        "commentary_count": len(pack_json.get("commentaries") or []),
        "risk_flag_count": len(pack_json.get("risk_flags") or []),
        "sample_variance_items": (pack_json.get("variance_items") or [])[:5],
        "all_amount_strings_sample": sorted(result.pack.all_amount_strings())[:30],
    }
    print(json.dumps(summary, indent=2, default=str))

    print("\n=== RAW LLM ANSWER ===")
    print(json.dumps(result.raw_answer.model_dump(mode="json"), indent=2, default=str))
    print("model_used:", result.model_used)
    print(
        "tokens:",
        {
            "prompt": result.prompt_tokens,
            "completion": result.completion_tokens,
            "total": result.total_tokens,
        },
    )

    print("\n=== GROUNDED ANSWER ===")
    print(json.dumps(result.grounded.model_dump(mode="json"), indent=2, default=str))
    print("dropped_sentence_count:", result.grounded.dropped_sentence_count)
    print("turn_id:", result.turn_id)
    print("processing_job_id:", result.processing_job_id)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
