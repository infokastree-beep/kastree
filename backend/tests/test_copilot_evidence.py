"""Unit tests for Copilot evidence-pack assembly (amounts as strings)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from app.schemas.commentary import BusinessHealthResult, CommentaryRecord
from app.schemas.copilot import REFUSAL_MESSAGE, CopilotIntent, CopilotToolName
from app.schemas.risk import AffectedAccount, RiskFlagRecord
from app.schemas.variance import VarianceItemRecord
from app.services.copilot_evidence import build_evidence_pack
from app.services.performance import build_period_metrics


def _company_ctx() -> dict[str, object]:
    return {
        "company_id": uuid4(),
        "company_name": "Acme Ltd",
        "tb_id": uuid4(),
        "period_end": date(2026, 9, 30),
        "prior_period_end": date(2026, 8, 31),
        "currency": "EUR",
    }


def _period(*, tb_id, period_end: date, revenue: str = "100000.00") -> object:
    return build_period_metrics(
        tb_id=tb_id,
        period_end=period_end,
        line_amounts={
            "revenue": Decimal(revenue),
            "gross_profit": Decimal("40000.00"),
            "net_profit": Decimal("12000.00"),
            "cash": Decimal("25000.00"),
            "cost_of_sales": Decimal("60000.00"),
            "operating_expenses": Decimal("20000.00"),
            "depreciation": Decimal("8000.00"),
        },
    )


def test_unsupported_question_refuses_without_tools() -> None:
    ctx = _company_ctx()
    pack = build_evidence_pack(
        question="What should we cut from the budget?",
        periods=[_period(tb_id=ctx["tb_id"], period_end=ctx["period_end"])],  # type: ignore[arg-type]
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.UNSUPPORTED
    assert pack.tools_used == []
    assert pack.refusal_reason == REFUSAL_MESSAGE
    assert pack.periods == []
    assert pack.all_amount_strings() == set()


def test_variance_pack_uses_string_amounts_only() -> None:
    ctx = _company_ctx()
    items = [
        VarianceItemRecord(
            line_item_code="revenue",
            line_item_name="Revenue",
            current_amount="120000.00",
            prior_amount="100000.00",
            variance_amount="20000.00",
            variance_pct="20.00",
            direction="increase",
            is_material=True,
        ),
        VarianceItemRecord(
            line_item_code="operating_expenses",
            line_item_name="Operating expenses",
            current_amount="21000.00",
            prior_amount="20000.00",
            variance_amount="1000.00",
            variance_pct="5.00",
            direction="increase",
            is_material=False,
        ),
    ]
    commentaries = {
        "revenue": CommentaryRecord(
            text="Further investigation required.",
            reasoning="Directional only.",
            confidence="medium",
        ),
    }
    pack = build_evidence_pack(
        question="What moved vs prior?",
        variance_items=items,
        commentaries=commentaries,
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.VARIANCE
    assert CopilotToolName.GET_VARIANCE in pack.tools_used
    assert pack.refusal_reason is None
    assert len(pack.variance_items) == 2
    assert pack.variance_items[0].current_amount == "120000.00"
    assert isinstance(pack.variance_items[0].current_amount, str)
    assert "20000.00" in pack.all_amount_strings()
    assert "20.00" in pack.all_amount_strings()
    assert "revenue" in pack.all_line_codes()
    assert len(pack.commentaries) == 1


def test_material_items_filters_non_material() -> None:
    ctx = _company_ctx()
    items = [
        VarianceItemRecord(
            line_item_code="revenue",
            line_item_name="Revenue",
            current_amount="120000.00",
            prior_amount="100000.00",
            variance_amount="20000.00",
            variance_pct="20.00",
            direction="increase",
            is_material=True,
        ),
        VarianceItemRecord(
            line_item_code="cash",
            line_item_name="Cash",
            current_amount="25100.00",
            prior_amount="25000.00",
            variance_amount="100.00",
            variance_pct="0.40",
            direction="increase",
            is_material=False,
        ),
    ]
    pack = build_evidence_pack(
        question="What are the material variances?",
        variance_items=items,
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.MATERIAL_ITEMS
    assert [row.line_code for row in pack.variance_items] == ["revenue"]
    assert "100.00" not in pack.all_amount_strings()


def test_expense_mix_and_period_metrics_as_strings() -> None:
    ctx = _company_ctx()
    period = _period(tb_id=ctx["tb_id"], period_end=ctx["period_end"])  # type: ignore[arg-type]
    pack = build_evidence_pack(
        question="Show the expense mix",
        periods=[period],  # type: ignore[arg-type]
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.EXPENSE_MIX
    assert {row.line_code for row in pack.expense_mix} == {
        "cost_of_sales",
        "operating_expenses",
        "depreciation",
    }
    assert all(isinstance(row.amount, str) for row in pack.expense_mix)
    assert pack.periods[0].metrics["revenue"] == "100000.00"
    assert isinstance(pack.periods[0].metrics["revenue"], str)


def test_trend_includes_multi_period_history() -> None:
    ctx = _company_ctx()
    prior_tb = uuid4()
    periods = [
        _period(tb_id=prior_tb, period_end=date(2026, 8, 31), revenue="90000.00"),
        _period(tb_id=ctx["tb_id"], period_end=ctx["period_end"], revenue="100000.00"),  # type: ignore[arg-type]
    ]
    pack = build_evidence_pack(
        question="How has revenue moved over 2 periods?",
        periods=periods,  # type: ignore[arg-type]
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.TREND
    assert len(pack.periods) == 2
    amounts = pack.all_amount_strings()
    assert "90000.00" in amounts
    assert "100000.00" in amounts


def test_risk_health_pack() -> None:
    ctx = _company_ctx()
    flags = [
        RiskFlagRecord(
            rule_name="negative_cash",
            severity="critical",
            description="Cash balance is negative.",
            recommended_action="Review bank reconciliations.",
            affected_accounts=[
                AffectedAccount(
                    account_code="1000",
                    account_name="Bank",
                    net_balance="-500.00",
                )
            ],
        )
    ]
    health = BusinessHealthResult(
        summary="Cash position is declining.",
        key_points=["Margin improving.", "Expense growth faster than revenue.", "Cash declining."],
        confidence="medium",
    )
    pack = build_evidence_pack(
        question="What risk flags are open?",
        risk_flags=flags,
        health=health,
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.RISK_HEALTH
    assert len(pack.risk_flags) == 1
    assert pack.risk_flags[0].affected_account_codes == ["1000"]
    assert pack.health is not None
    assert pack.health.summary.startswith("Cash")
    # Risk descriptions are text — monetary values in affected_accounts are NOT
    # promoted into all_amount_strings (evidence pack keeps flag text, not TB dumps).
    assert "-500.00" not in pack.all_amount_strings()


def test_glossary_hit_and_miss() -> None:
    ctx = _company_ctx()
    hit = build_evidence_pack(
        question="What does gross profit mean?",
        **ctx,  # type: ignore[arg-type]
    )
    assert hit.intent == CopilotIntent.GLOSSARY
    assert hit.refusal_reason is None
    assert hit.glossary[0].term == "gross profit"

    miss = build_evidence_pack(
        question="What does amortised cost mean?",
        **ctx,  # type: ignore[arg-type]
    )
    assert miss.intent == CopilotIntent.GLOSSARY
    assert miss.refusal_reason == REFUSAL_MESSAGE
    assert miss.glossary == []


def test_missing_tool_data_refuses() -> None:
    ctx = _company_ctx()
    pack = build_evidence_pack(
        question="What moved vs prior?",
        variance_items=[],
        **ctx,  # type: ignore[arg-type]
    )
    assert pack.intent == CopilotIntent.VARIANCE
    assert pack.refusal_reason == REFUSAL_MESSAGE
