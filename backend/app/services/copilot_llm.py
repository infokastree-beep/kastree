"""Copilot LLM call — GPT-4o → GPT-4o-mini → refusal.

The model receives system rules + the evidence pack + the user question and
must return the CopilotAnswer JSON schema. It is never trusted to self-police
figures; ``ground_answer`` runs afterwards.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

from openai import OpenAI

from app.schemas.copilot import (
    REFUSAL_MESSAGE,
    CopilotAnswer,
    EvidencePack,
)

logger = logging.getLogger(__name__)

COPILOT_PRIMARY_MODEL = "gpt-4o"
COPILOT_FALLBACK_MODEL = "gpt-4o-mini"
COPILOT_TEMPERATURE = 0.2
# 1 initial + 3 retries with exponential backoff, per model.
LLM_MAX_ATTEMPTS = 4
LLM_BACKOFF_SECONDS = (1, 2, 4)

SleepFn = Callable[[float], None]

COPILOT_SYSTEM_PROMPT = """\
You are Kastree Copilot, an assistant for accountants reviewing management accounts.

You answer ONLY from the evidence pack JSON provided. Rules:
- Do NOT invent figures, periods, accounts, or risks.
- Any money amount or percentage you mention MUST appear verbatim (same digits) \
in the evidence pack. Prefer the pack's string forms (e.g. "816600.00").
- If the evidence pack cannot answer the question, set refused=true and use the \
refusal_message exactly: "I don't have that in the evidence for this period."
- Never give forecasts, tax advice, journal entries, or "what to cut" recommendations.
- Cite sources with the citations array. source must be one of: performance, \
variance, expense_mix, risk, commentary, health, glossary. Include line_code \
and period_end when applicable.
- Respond as a single JSON object with this schema:
{
  "answer_markdown": "string",
  "citations": [{"source": "variance", "line_code": "revenue", "period_end": "YYYY-MM-DD"}],
  "confidence": "high|medium|low",
  "refused": false,
  "refusal_message": null
}
"""

COPILOT_PROMPT_VERSION = "copilot_v1_2026-09-06"


@dataclass(frozen=True, slots=True)
class CopilotLLMResult:
    answer: CopilotAnswer
    model_used: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def generate_copilot_answer(
    *,
    question: str,
    pack: EvidencePack,
    openai_client: OpenAI | None = None,
    sleep: SleepFn = time.sleep,
) -> CopilotLLMResult:
    """Call GPT-4o then GPT-4o-mini; refuse if both fail or pack already refused."""
    if pack.refusal_reason:
        return CopilotLLMResult(
            answer=CopilotAnswer(
                answer_markdown="",
                refused=True,
                refusal_message=pack.refusal_reason or REFUSAL_MESSAGE,
            ),
            model_used=None,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
        )

    client = openai_client if openai_client is not None else OpenAI()
    user_prompt = (
        f"Evidence pack:\n{pack.model_dump_json()}\n\n"
        f"User question:\n{question.strip()}"
    )

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    last_error: Exception | None = None

    for model in (COPILOT_PRIMARY_MODEL, COPILOT_FALLBACK_MODEL):
        try:
            payload, usage = _complete_copilot_json(
                client,
                model=model,
                system_prompt=COPILOT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                sleep=sleep,
            )
            prompt_tokens += int(usage.get("prompt_tokens") or 0)
            completion_tokens += int(usage.get("completion_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)
            answer = CopilotAnswer.model_validate(payload)
            return CopilotLLMResult(
                answer=answer,
                model_used=model,
                prompt_tokens=prompt_tokens or None,
                completion_tokens=completion_tokens or None,
                total_tokens=total_tokens or None,
            )
        except Exception as exc:
            last_error = exc
            logger.warning("Copilot LLM model %s failed: %s", model, exc)

    logger.error(
        "Copilot LLM unavailable after gpt-4o and gpt-4o-mini: %s",
        last_error,
    )
    return CopilotLLMResult(
        answer=CopilotAnswer(
            answer_markdown="",
            refused=True,
            refusal_message=REFUSAL_MESSAGE,
        ),
        model_used=None,
        prompt_tokens=prompt_tokens or None,
        completion_tokens=completion_tokens or None,
        total_tokens=total_tokens or None,
    )


def _complete_copilot_json(
    client: OpenAI,
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    sleep: SleepFn,
) -> tuple[dict[str, Any], dict[str, int | None]]:
    """Four attempts on a single model (1 initial + 3 retries)."""
    last_error: Exception | None = None
    for attempt in range(LLM_MAX_ATTEMPTS):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=COPILOT_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty LLM response content")
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise ValueError("LLM response is not a JSON object")
            usage_obj = getattr(response, "usage", None)
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
                "completion_tokens": getattr(usage_obj, "completion_tokens", None),
                "total_tokens": getattr(usage_obj, "total_tokens", None),
            }
            return payload, usage
        except Exception as exc:
            last_error = exc
            if attempt < LLM_MAX_ATTEMPTS - 1:
                sleep(LLM_BACKOFF_SECONDS[attempt])
    assert last_error is not None
    raise last_error
