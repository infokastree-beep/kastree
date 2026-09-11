#!/usr/bin/env python3
"""Measure Business Health differentiation across contrasting metric profiles.

Usage:
  OPENAI_API_KEY=sk-... .venv/bin/python scripts/measure_business_health_quality.py

Without a real key, prints differentiated *user prompts* (deterministic) and
records that the live system prompt includes anti-template / dominant-story
guards (v2). With a real key, also scores banned-filler hits and pairwise
summary similarity across improving / declining / mixed profiles.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.commentary import (  # noqa: E402
    _build_business_health_user_prompt,
    generate_business_health_summary,
)
from app.services.llm import BUSINESS_HEALTH_SYSTEM  # noqa: E402

BANNED_FILLERS = [
    "mixed financial trends",
    "some areas improving, others need attention",
    "overall the business shows",
    "maintaining a stable financial position",
    "balanced financial structure",
    "consistent performance across key metrics",
    "some areas improving",
    "others need attention",
]


@dataclass(frozen=True)
class _Line:
    line_item_code: str
    amount: Decimal
    is_subtotal: bool = False


def _lines(mapping: dict[str, str]) -> list[_Line]:
    return [_Line(code, Decimal(val)) for code, val in mapping.items()]


PROFILES = {
    "improving": {
        "cur_sopl": {
            "revenue": "2000",
            "cost_of_sales": "800",
            "operating_expenses": "500",
        },
        "prior_sopl": {
            "revenue": "1000",
            "cost_of_sales": "500",
            "operating_expenses": "400",
        },
        "cur_sofp": {"cash": "800", "loans": "100"},
        "prior_sofp": {"cash": "300", "loans": "400"},
    },
    "declining": {
        "cur_sopl": {
            "revenue": "900",
            "cost_of_sales": "700",
            "operating_expenses": "500",
        },
        "prior_sopl": {
            "revenue": "1500",
            "cost_of_sales": "600",
            "operating_expenses": "300",
        },
        "cur_sofp": {"cash": "50", "loans": "900"},
        "prior_sofp": {"cash": "500", "loans": "200"},
    },
    "mixed": {
        "cur_sopl": {
            "revenue": "1200",
            "cost_of_sales": "480",
            "operating_expenses": "360",
        },
        "prior_sopl": {
            "revenue": "1000",
            "cost_of_sales": "500",
            "operating_expenses": "300",
        },
        "cur_sofp": {"cash": "120", "loans": "600"},
        "prior_sofp": {"cash": "400", "loans": "350"},
    },
}


def _token_set(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "that", "this", "from", "while"}
    return {t for t in re.findall(r"[a-z]{3,}", text.lower()) if t not in stop}


def _jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main() -> int:
    out: dict = {
        "prompt_version_markers": {
            "has_anti_template": "Anti-template" in BUSINESS_HEALTH_SYSTEM,
            "bans_mixed_filler": "mixed financial trends" in BUSINESS_HEALTH_SYSTEM,
            "has_dominant_story": "clearly improving" in BUSINESS_HEALTH_SYSTEM,
        },
        "user_prompts": {},
        "llm_outputs": {},
        "scores": {},
    }

    for name, p in PROFILES.items():
        args = (
            _lines(p["cur_sopl"]),
            _lines(p["prior_sopl"]),
            _lines(p["cur_sofp"]),
            _lines(p["prior_sofp"]),
        )
        user = _build_business_health_user_prompt(*args)
        out["user_prompts"][name] = user
        print(f"\n=== {name} USER PROMPT ===\n{user}")

    key = os.environ.get("OPENAI_API_KEY", "")
    live = bool(key) and not key.startswith("sk-local") and len(key) > 30
    out["live_llm"] = live

    if not live:
        print(
            "\nNo real OPENAI_API_KEY — wrote deterministic user-prompt + prompt-marker evidence only."
        )
        dest = Path("/opt/cursor/artifacts/live-qa/bh_quality_measure.json")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(out, indent=2))
        print("Wrote", dest)
        return 0

    for name, p in PROFILES.items():
        args = (
            _lines(p["cur_sopl"]),
            _lines(p["prior_sopl"]),
            _lines(p["cur_sofp"]),
            _lines(p["prior_sofp"]),
        )
        result = generate_business_health_summary(*args)
        out["llm_outputs"][name] = {
            "summary": result.summary,
            "key_points": list(result.key_points),
            "confidence": result.confidence,
        }
        text = " ".join([result.summary, *result.key_points]).lower()
        filler_hits = [f for f in BANNED_FILLERS if f in text]
        out["scores"][name] = {"banned_filler_hits": filler_hits}
        print(f"\n=== {name} OUTPUT ===\n{result.summary}")
        for i, kp in enumerate(result.key_points, 1):
            print(f"  {i}. {kp}")
        print("filler_hits", filler_hits)

    names = list(out["llm_outputs"])
    pairwise = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pairwise[f"{a}_vs_{b}"] = round(
                _jaccard(
                    out["llm_outputs"][a]["summary"],
                    out["llm_outputs"][b]["summary"],
                ),
                3,
            )
    out["scores"]["pairwise_summary_jaccard"] = pairwise
    print("\nPairwise summary Jaccard:", pairwise)

    dest = Path("/opt/cursor/artifacts/live-qa/bh_quality_measure.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2))
    print("Wrote", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
