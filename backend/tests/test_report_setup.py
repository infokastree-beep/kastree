"""Report setup is display-only, and the sidebar catalogue follows the framework."""

from __future__ import annotations

import inspect
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal, set_rls_org_id
from app.routers import year_ends as year_end_router
from app.services import draft_workflow, statutory_present, statutory_statements
from app.services.report_setup import display_amount, save_report_setup, sections_for
from tests.conftest import auth_headers
from tests.test_adopted_trial_balance import _insert_tb

_ROOT = Path(__file__).resolve().parents[1]


def test_display_rounding_returns_a_new_string_and_leaves_the_decimal() -> None:
    amount = Decimal("18400.40")
    assert display_amount(amount, "unit") == "18400"
    assert display_amount(amount, "thousands") == "18"
    assert amount == Decimal("18400.40")

    half = Decimal("10.50")
    assert display_amount(half, "unit") == "11"
    assert half == Decimal("10.50")
    assert display_amount(Decimal("-10.50"), "unit") == "-11"
    assert display_amount(Decimal("18500"), "thousands") == "19"
    assert display_amount(Decimal("-18500"), "thousands") == "-19"


def test_sidebar_sections_follow_the_reporting_framework() -> None:
    frs = sections_for("frs102-1a-ie")
    labels = [section.label for section in frs]
    form11 = [section.label for section in sections_for("form11-summary")]
    unknown = [section.label for section in sections_for("uk-frs105")]
    pack_labels = [
        "Cover",
        "Contents",
        "Directors and other information",
        "Directors' report",
        "Directors' responsibilities statement",
        "Compilation report",
        "Income statement",
        "Statement of comprehensive income",
        "Statement of financial position",
        "Statement of changes in equity",
        "Cash flow statement",
        "Notes",
        "Supplementary trading statement",
    ]

    assert labels[:6] == [
        "Review dashboard",
        "Report setup",
        "Mapping",
        "Adjustments",
        "Disclosures",
        "Company details",
    ]
    assert labels[6] == "Sections setup"
    assert labels[7:-1] == pack_labels
    assert labels[-1] == "Draft PDF"
    assert [section.group for section in frs] == [
        "overview",
        "report-options",
        "inputs",
        "inputs",
        "inputs",
        "inputs",
        *["sections"] * (len(pack_labels) + 1),
        "outputs",
    ]
    setup = next(section for section in frs if section.id == "sections-setup")
    assert setup.lock is None
    assert setup.built is None
    assert setup.order == 7
    from pydantic import ValidationError

    from app.schemas.report_setup import ReportSetupWrite

    with pytest.raises(ValidationError, match="Unknown section sections-setup"):
        ReportSetupWrite.model_validate(
            {
                "rounding": "unit",
                "statement_type": "draft",
                "face_dates": {},
                "column_headers": {
                    "as_at_current": "2026",
                    "as_at_prior": "2025",
                    "ended_current": "2026",
                    "ended_prior": "2025",
                },
                "sections": {"sections-setup": True},
            }
        )
    cover = next(section for section in frs if section.id == "cover")
    income = next(section for section in frs if section.id == "income")
    cash = next(section for section in frs if section.id == "cash-flow")
    pdf = next(section for section in frs if section.id == "draft-pdf")
    assert cover.lock == "user"
    assert cover.default == "on"
    assert cover.built is True
    assert income.lock == "locked"
    assert income.built is True
    assert cash.lock == "user"
    assert cash.default == "off"
    assert cash.built is False
    assert pdf.group == "outputs"
    assert pdf.lock is None
    assert form11 == [
        "Review dashboard",
        "Report setup",
    ]
    assert [section.group for section in sections_for("form11-summary")] == [
        "overview",
        "report-options",
    ]
    assert "Mapping" not in form11
    assert "Extracts summary" not in frs
    assert "Extracts summary" not in form11
    assert len(form11) < len(frs)
    assert unknown == ["Review dashboard", "Report setup"]
    assert unknown != frs


def test_statement_build_does_not_read_report_setup() -> None:
    for module in (statutory_statements, statutory_present, draft_workflow):
        source = inspect.getsource(module)
        assert "report_setup" not in source
    save_source = inspect.getsource(save_report_setup)
    assert "statements_for_adopted" not in save_source
    assert "recompute" not in save_source


def _snapshot(org_id: uuid.UUID, year_end_id: str) -> tuple[object, ...]:
    with SyncSessionLocal() as session:
        set_rls_org_id(session, org_id)
        row = session.execute(
            text(
                """
                SELECT ye.period_start::text,
                       ye.period_end::text,
                       ye.pack_id,
                       ye.pack_version,
                       ye.adopted_trial_balance_id::text,
                       ye.prior_year_validated,
                       ye.first_financial_period,
                       d.row_version,
                       md5(tb.parsed_data::text)
                FROM findraft_year_ends ye
                JOIN findraft_draft_versions d
                  ON d.year_end_id = ye.id
                JOIN trial_balances tb
                  ON tb.id = ye.adopted_trial_balance_id
                WHERE ye.id = :id
                ORDER BY d.version_number DESC
                LIMIT 1
                """
            ),
            {"id": year_end_id},
        ).one()
    return tuple(row)


def _figures(body: dict[str, object]) -> dict[str, object]:
    def rows(name: str) -> list[tuple[object, object, object]]:
        raw = body[name]
        assert isinstance(raw, list)
        return [
            (row["label"], row["current"], row["prior"])
            for row in raw
            if isinstance(row, dict)
        ]

    return {
        "profit": body["profit"],
        "net_assets": body["net_assets"],
        "watermark": body["watermark"],
        "income": rows("income"),
        "sofp": rows("sofp"),
    }


@pytest.mark.asyncio
async def test_report_setup_does_not_change_stored_figures_or_rebuild(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = provisioned_org["org_id"]
    assert isinstance(org_id, uuid.UUID)
    company_id = provisioned_org["company_id"]
    assert isinstance(company_id, uuid.UUID)
    token = provisioned_org["token"]
    assert isinstance(token, str)
    tb_id = _insert_tb(
        org_id=org_id,
        company_id=company_id,
        rows=(
            ("2130", "Bank current account", "18400.40", "0.00", "18400.40", "cash"),
            (
                "3000",
                "Called up share capital",
                "0.00",
                "18400.40",
                "-18400.40",
                "share_capital",
            ),
        ),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
    )
    headers = auth_headers(token)
    opened = await api_client.post(
        f"/trial-balances/{tb_id}/statutory-year-end",
        headers=headers,
        json={},
    )
    assert opened.status_code == 200, opened.text
    year_end_id = opened.json()["year_end_id"]
    gate = await api_client.post(
        f"/year-ends/{year_end_id}/first-financial-period",
        headers=headers,
    )
    assert gate.status_code == 200, gate.text
    before = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert before.status_code == 200, before.text
    figures = _figures(before.json())
    assert figures["net_assets"] == "18400.40"
    anchor = _snapshot(org_id, year_end_id)
    draft = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert draft.status_code == 200, draft.text
    row_version = draft.json()["row_version"]

    def _refuse_rebuild(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("statement rebuild was called")

    original_build = statutory_statements.statements_for_adopted
    original_route = year_end_router.statements_for_adopted
    monkeypatch.setattr(
        "app.services.statutory_statements.statements_for_adopted",
        _refuse_rebuild,
    )
    monkeypatch.setattr(
        "app.routers.year_ends.statements_for_adopted",
        _refuse_rebuild,
    )
    saved = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "thousands",
            "statement_type": "compilation",
            "face_dates": {
                "current_start": "2024-04-01",
                "current_end": "2025-03-31",
                "prior_start": "2023-04-01",
                "prior_end": "2024-03-31",
            },
            "column_headers": {
                "as_at_current": "as at 31 March 2025",
                "as_at_prior": "as at 31 March 2024",
                "ended_current": "year ended 31 March 2025",
                "ended_prior": "year ended 31 March 2024",
            },
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["rounding"] == "thousands"
    assert body["statement_type"] == "compilation"
    assert body["face_dates"]["current_end"] == "2025-03-31"
    assert body["column_headers"]["ended_current"] == "year ended 31 March 2025"
    assert body["trial_balance_period_start"] == "2026-01-01"
    assert body["trial_balance_period_end"] == "2026-12-31"
    assert body["basis_id"] == "frs102-1a-ie"
    assert body["currency"] == "GBP"
    assert body["rounding_unit_label"] == "Nearest pound"
    assert body["rounding_thousands_label"] == "Nearest £'000"
    monkeypatch.setattr(
        "app.services.statutory_statements.statements_for_adopted",
        original_build,
    )
    monkeypatch.setattr(
        "app.routers.year_ends.statements_for_adopted",
        original_route,
    )

    after = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert after.status_code == 200, after.text
    assert _figures(after.json()) == figures
    assert _snapshot(org_id, year_end_id) == anchor
    again = await api_client.get(f"/year-ends/{year_end_id}/draft", headers=headers)
    assert again.json()["row_version"] == row_version

    refused = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "unit",
            "statement_type": "audit",
            "face_dates": {
                "current_start": "2026-01-01",
                "current_end": "2026-12-31",
                "prior_start": None,
                "prior_end": None,
            },
            "column_headers": {
                "as_at_current": "2026",
                "as_at_prior": "2025",
                "ended_current": "2026",
                "ended_prior": "2025",
            },
        },
    )
    assert refused.status_code == 422, refused.text
    review = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json={
            "rounding": "unit",
            "statement_type": "review",
            "face_dates": {
                "current_start": "2026-01-01",
                "current_end": "2026-12-31",
                "prior_start": None,
                "prior_end": None,
            },
            "column_headers": {
                "as_at_current": "2026",
                "as_at_prior": "2025",
                "ended_current": "2026",
                "ended_prior": "2025",
            },
        },
    )
    assert review.status_code == 422, review.text
    still = await api_client.get(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
    )
    assert still.json()["statement_type"] == "compilation"
    assert still.json()["rounding"] == "thousands"
    assert still.json()["sections"] is None
    assert _snapshot(org_id, year_end_id) == anchor

    def _display(sections: dict[str, bool] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "rounding": "thousands",
            "statement_type": "compilation",
            "face_dates": {
                "current_start": "2024-04-01",
                "current_end": "2025-03-31",
                "prior_start": "2023-04-01",
                "prior_end": "2024-03-31",
            },
            "column_headers": {
                "as_at_current": "as at 31 March 2025",
                "as_at_prior": "as at 31 March 2024",
                "ended_current": "year ended 31 March 2025",
                "ended_prior": "year ended 31 March 2024",
            },
        }
        if sections is not None:
            payload["sections"] = sections
        return payload

    for locked_id in ("income", "sofp", "notes"):
        locked = await api_client.put(
            f"/year-ends/{year_end_id}/report-setup",
            headers=headers,
            json=_display({locked_id: False, "cover": False}),
        )
        assert locked.status_code == 422, locked.text
        assert "Locked section cannot be turned off" in locked.text
        unchanged = await api_client.get(
            f"/year-ends/{year_end_id}/report-setup",
            headers=headers,
        )
        assert unchanged.json()["sections"] is None
        assert unchanged.json()["rounding"] == "thousands"

    unknown = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display({"auditor": True}),
    )
    assert unknown.status_code == 422, unknown.text

    toggled = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display({"cover": False, "cash-flow": True, "income": True}),
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["sections"] == {
        "cover": False,
        "cash-flow": True,
        "income": True,
    }
    kept = await api_client.put(
        f"/year-ends/{year_end_id}/report-setup",
        headers=headers,
        json=_display(),
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["sections"] == {
        "cover": False,
        "cash-flow": True,
        "income": True,
    }
    after_toggle = await api_client.get(
        f"/year-ends/{year_end_id}/adopted-trial-balance/statements",
        headers=headers,
    )
    assert after_toggle.status_code == 200, after_toggle.text
    assert _figures(after_toggle.json()) == figures
    assert _snapshot(org_id, year_end_id) == anchor


@pytest.mark.asyncio
async def test_framework_catalogue_is_not_a_single_frs_list(
    api_client: AsyncClient,
    provisioned_org: dict[str, object],
) -> None:
    token = provisioned_org["token"]
    assert isinstance(token, str)
    listed = await api_client.get(
        "/year-ends/frameworks",
        headers=auth_headers(token),
    )
    assert listed.status_code == 200, listed.text
    frameworks = {item["id"]: item for item in listed.json()["frameworks"]}
    assert set(frameworks) == {"frs102-1a-ie", "form11-summary"}
    frs_labels = [
        section["label"] for section in frameworks["frs102-1a-ie"]["sections"]
    ]
    form_labels = [
        section["label"] for section in frameworks["form11-summary"]["sections"]
    ]
    assert frs_labels == [section.label for section in sections_for("frs102-1a-ie")]
    assert form_labels == [section.label for section in sections_for("form11-summary")]
    assert frameworks["frs102-1a-ie"]["available"] is True
    assert frameworks["form11-summary"]["available"] is False
    assert "Mapping" in frs_labels
    assert "Company details" in frs_labels
    frs_groups = [
        section["group"] for section in frameworks["frs102-1a-ie"]["sections"]
    ]
    form_groups = [
        section["group"] for section in frameworks["form11-summary"]["sections"]
    ]
    assert "sections" in frs_groups
    assert "sections" not in form_groups
    assert "inputs" not in form_groups
    assert "Extracts summary" not in form_labels
    assert "Extracts summary" not in frs_labels
    by_id = {
        section["id"]: section for section in frameworks["frs102-1a-ie"]["sections"]
    }
    assert by_id["income"]["built"] is True
    assert by_id["cover"]["built"] is True
    assert by_id["oci"]["built"] is False
    assert by_id["socie"]["built"] is False
    assert by_id["cash-flow"]["built"] is False
    assert by_id["trading"]["built"] is False
    assert by_id["draft-pdf"]["built"] is None


def test_engine_sources_have_no_report_setup_import() -> None:
    for name in (
        "app/services/statutory_statements.py",
        "app/services/statutory_present.py",
        "app/services/draft_workflow.py",
    ):
        source = (_ROOT / name).read_text(encoding="utf-8")
        assert "report_setup" not in source
    engine = _ROOT.parent / "findraft" / "engine"
    for path in engine.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "report_setup" not in source
        assert "statutory_compose" not in source


def test_pack_declares_section_locks_and_defaults() -> None:
    from app.schemas.report_setup import pack_section_catalogue

    catalogue = pack_section_catalogue()
    assert set(catalogue) == {
        "cover",
        "contents",
        "directors-info",
        "directors-report",
        "directors-responsibilities",
        "compilation",
        "income",
        "oci",
        "sofp",
        "socie",
        "cash-flow",
        "notes",
        "trading",
    }
    locked = sorted(
        section_id for section_id, rule in catalogue.items() if rule["lock"] == "locked"
    )
    assert locked == ["income", "notes", "sofp"]
    assert catalogue["income"]["default"] == "on"
    assert catalogue["oci"]["default"] == "engine"
    assert catalogue["cash-flow"]["default"] == "off"
    assert catalogue["trading"]["default"] == "off"
    assert catalogue["cover"]["source_status"] == "pending-reviewer-signoff"
    assert catalogue["notes"]["group"] == "frs-locked"


def test_not_built_comes_from_the_pack_flag() -> None:
    import json

    pack = json.loads(
        (_ROOT.parent / "findraft/content/frs102-1a-ie/2024.09/pack.json").read_text(
            encoding="utf-8"
        )
    )
    declared = pack["sections"]
    assert isinstance(declared, list)
    served = {section.id: section for section in sections_for("frs102-1a-ie")}
    flagged: list[str] = []
    for item in declared:
        assert isinstance(item, dict)
        section_id = item["id"]
        assert isinstance(section_id, str)
        expected = True if "built" not in item else item["built"]
        assert isinstance(expected, bool)
        assert served[section_id].built is expected
        if expected is False:
            flagged.append(section_id)
    assert flagged == ["oci", "socie", "cash-flow", "trading"]
    source = (_ROOT / "app/services/report_setup.py").read_text(encoding="utf-8")
    assert "_NOT_BUILT" not in source
    for token in ("oci", "socie", "cash-flow", "trading"):
        assert token not in source


def test_company_column_migration_grants_are_explicit() -> None:
    source = (
        _ROOT
        / "alembic"
        / "versions"
        / "f2a3b4c5d6_company_advisers_and_share_classes.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "f2a3b4c5d6"' in source
    assert 'down_revision: Union[str, None] = "e1f2a3b4c5"' in source
    assert "ADD COLUMN advisers JSONB" in source
    assert "ADD COLUMN share_classes JSONB" in source
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.companies TO findraft"
        in source
    )
    assert (
        "REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLE public.companies FROM findraft"
        in source
    )
    assert "GRANT ALL" not in source


def test_notes_children_come_from_the_pack() -> None:
    from app.services.report_setup import section_children_marker

    notes = next(section for section in sections_for("frs102-1a-ie") if section.id == "notes")
    assert notes.children == "printed-notes"
    cover = next(section for section in sections_for("frs102-1a-ie") if section.id == "cover")
    assert cover.children is None
    assert section_children_marker({"children": "printed-notes"}) == "printed-notes"
    assert section_children_marker({}) is None
    assert (
        section_children_marker(
            {"children": [{"id": "approval", "label": "Approval"}]}
        )
        == "declared"
    )
    with pytest.raises(ValueError, match="children are malformed"):
        section_children_marker({"children": "made-up"})


def test_company_model_maps_advisers_and_share_classes() -> None:
    """Migration f2a3b4c5d6 is applied. The form and the note may read them."""
    from app.models.company import Company

    assert Company.__table__.c.advisers.nullable is True
    assert Company.__table__.c.share_classes.nullable is True
