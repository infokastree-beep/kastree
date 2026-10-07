"""Week 11 statutory pages and the DOCX render job."""

from __future__ import annotations

import subprocess
import sys
import uuid
import zipfile
from collections.abc import Iterator
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SyncSessionLocal
from app.main import app
from app.services.docx_child import RENDER_AS_LIMIT
from app.services.render_jobs import process_render_job
from app.services.source_storage import LocalPracticeStorage, get_source_storage
from app.services.statutory_docx import escape_export_text
from app.services.statutory_pages import build_statutory_pages
from tests.conftest import auth_headers, make_access_token
from tests.test_draft_locking import _answer_disclosures, _draft_path
from tests.test_organisations_api import _add_org_user
from tests.test_reconciliation import _TINY, _import_csv
from tests.test_role_enforcement import _set_role
from tests.test_statutory_statements import (
    _entity,
    _golden,
    _ready_golden,
    _statements_path,
)
from tests.test_tb_ingestion import _year_end

_FORBIDDEN = "You don't have permission to access this resource."
_NOT_RENDERABLE = "Statutory statements are not renderable"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_FORMULA_NAME = '=HYPERLINK("http://evil")'


@pytest.fixture
def stored_files(tmp_path: Path) -> Iterator[LocalPracticeStorage]:
    store = LocalPracticeStorage(tmp_path)
    app.dependency_overrides[get_source_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_source_storage, None)


def _page(document, heading: str) -> str:
    page = next(item for item in document.pages if item.heading == heading)
    return "\n".join(page.paragraphs)


def test_statement_snapshot_without_pages_still_validates() -> None:
    from app.schemas.year_end import StatementResponse

    parsed = StatementResponse.model_validate(
        {
            "watermark": "FINAL",
            "renderable": True,
            "blocked": False,
            "build_error": None,
            "checks": [],
            "net_assets": "1.00",
            "profit": "1.00",
            "compliance_statement": "Recorded.",
            "sofp": [],
            "income": [],
            "notes": [],
            "rounding_flags": [],
        }
    )
    assert parsed.pages == []
    assert parsed.company_name == ""


def test_escape_export_text_prefixes_formula_leads() -> None:
    assert escape_export_text("=1+1") == "'=1+1"
    assert escape_export_text("+1") == "'+1"
    assert escape_export_text("-1") == "'-1"
    assert escape_export_text("@cmd") == "'@cmd"
    assert escape_export_text("Revenue") == "Revenue"
    assert escape_export_text("157650.00") == "157650.00"


def test_pages_keep_engine_figures_and_leave_gaps() -> None:
    document = _golden()
    assert document.net_assets == Decimal("455812.00")
    assert document.profit == Decimal("157650.00")
    assert [page.heading for page in document.pages] == [
        "Compilation report",
        "Directors' report",
        "Approval of the financial statements",
        "Audit exemption",
    ]
    assert document.html is not None
    assert document.html.index("Compilation report") < document.html.index(
        "Statement of financial position"
    )
    assert document.html.index("Audit exemption") < document.html.index(
        "Statement of financial position"
    )
    compilation = _page(document, "Compilation report")
    assert "The practice name has not been recorded." in compilation
    assert "not an audit" in compilation
    assert "not a review" in compilation
    assert "No audit opinion" in compilation
    report = _page(document, "Directors' report")
    assert "The financial year end has not been recorded." in report
    assert "Ada Lovelace" in report
    assert "The company secretary has not been recorded." in report
    assert "Principal activities have not been recorded." in report
    assert "Profit for the financial year is €157,650." in report
    assert "does not include a business review" in report
    assert "A dividend has not been recorded on this draft." in report
    approval = _page(document, "Approval of the financial statements")
    assert "Approval date has not been recorded." in approval
    assert "A signatory has not been separately recorded." in approval
    exemption = _page(document, "Audit exemption")
    assert "does not claim the audit exemption" in exemption
    assert "The size test has not been recorded." in exemption
    assert "section 335" not in exemption
    joined = " ".join(page.heading for page in document.pages).casefold()
    assert "auditor" not in joined


def test_size_eligibility_does_not_invent_a_section_335_declaration() -> None:
    eligible = build_statutory_pages(
        company_name="Northwind Limited",
        practice_name="Harbour Practice",
        period_end="2026-12-31",
        directors="Ada Lovelace",
        secretary="Grace Hopper",
        principal_activity="Software",
        currency="EUR",
        profit=Decimal("10.00"),
        size_eligible=True,
    )
    body = eligible[-1].paragraphs[0]
    assert "does not make the statement required by section 335" in body
    assert "have not recorded that they are availing" in body
    assert "section 334" in body
    refused = build_statutory_pages(
        company_name="Northwind Limited",
        practice_name="Harbour Practice",
        period_end="2026-12-31",
        directors="",
        secretary="",
        principal_activity="",
        currency="EUR",
        profit=Decimal("10.00"),
        size_eligible=False,
    )
    assert (
        "does not meet the pack's small-company conditions" in refused[-1].paragraphs[0]
    )
    assert "section 335" not in refused[-1].paragraphs[0]


def test_page_html_escapes_director_names() -> None:
    rendered = _golden(entity=_entity(directors_list="<script>alert(1)</script>"))
    assert rendered.html is not None
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered.html
    assert "auditor's report" not in rendered.html.casefold()


def test_build_docx_escapes_formula_leads(tmp_path: Path) -> None:
    from app.services.statutory_docx import build_docx

    dest = tmp_path / "escaped.docx"
    build_docx(
        {
            "watermark": "DRAFT",
            "company_name": '=HYPERLINK("http://evil")',
            "compliance_statement": "+see note",
            "pages": [
                {
                    "heading": "-Directors",
                    "paragraphs": ["@cmd"],
                }
            ],
            "sofp": [{"label": "Cash", "current": "-10.00", "prior": "0.00"}],
            "income": [],
            "notes": [],
        },
        dest,
    )
    xml = _xml(dest.read_bytes())
    assert "'=HYPERLINK" in xml
    assert "'+see note" in xml
    assert "'-Directors" in xml
    assert "'@cmd" in xml
    assert "'-10.00" in xml


def test_docx_child_sets_address_space_cap() -> None:
    backend = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.services.docx_child import apply_memory_cap; "
                "import resource; apply_memory_cap(); "
                "print(resource.getrlimit(resource.RLIMIT_AS)[0])"
            ),
        ],
        cwd=backend,
        check=True,
        capture_output=True,
        text=True,
    )
    assert int(completed.stdout.strip()) == RENDER_AS_LIMIT


def _docx_path(year_end_id: str, version_id: str) -> str:
    return f"{_statements_path(year_end_id, version_id)}.docx"


def _job_path(year_end_id: str, version_id: str, job_id: str) -> str:
    return (
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}"
        f"/render-jobs/{job_id}"
    )


def _process(org_id: uuid.UUID, job_id: str, storage: LocalPracticeStorage):
    with SyncSessionLocal() as session:
        return process_render_job(
            session,
            org_id=org_id,
            job_id=uuid.UUID(job_id),
            storage=storage,
        )


def _xml(content: bytes) -> str:
    assert content.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read("word/document.xml").decode()


@pytest.mark.asyncio
async def test_docx_job_escapes_formulas_and_replays(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    with SyncSessionLocal() as session:
        session.execute(
            text("UPDATE companies SET name = :name WHERE id = :id"),
            {"name": _FORMULA_NAME, "id": str(provisioned_org["company_id"])},
        )
        session.commit()
    headers = auth_headers(provisioned_org["token"])
    missing_key = await api_client.post(
        _docx_path(year_end_id, version_id), headers=headers
    )
    assert missing_key.status_code == 400
    created = await api_client.post(
        _docx_path(year_end_id, version_id),
        headers={**headers, "Idempotency-Key": "week11-docx"},
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["job_id"]
    assert created.json()["status"] == "pending"
    replay = await api_client.post(
        _docx_path(year_end_id, version_id),
        headers={**headers, "Idempotency-Key": "week11-docx"},
    )
    assert replay.status_code == 202, replay.text
    assert replay.json()["job_id"] == job_id
    early = await api_client.get(
        f"{_job_path(year_end_id, version_id, job_id)}/download",
        headers=headers,
    )
    assert early.status_code == 409
    processed = _process(provisioned_org["org_id"], job_id, stored_files)
    assert processed is not None
    assert processed.status == "ready"
    download = await api_client.get(
        f"{_job_path(year_end_id, version_id, job_id)}/download",
        headers=headers,
    )
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == _DOCX
    assert "statutory-statements-draft.docx" in download.headers["content-disposition"]
    xml = _xml(download.content)
    assert "'=HYPERLINK" in xml
    assert "Compilation report" in xml
    assert "auditor's report" not in xml.casefold()
    assert "455812.00" in xml
    assert "157650.00" in xml

    other = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="other.csv",
        content=_TINY.encode(),
        file_key="week11-other-file",
        version_key="week11-other-version",
        process=False,
    )
    conflict = await api_client.post(
        _docx_path(year_end_id, other),
        headers={**headers, "Idempotency-Key": "week11-docx"},
    )
    assert conflict.status_code == 409, conflict.text


@pytest.mark.asyncio
async def test_docx_refuses_viewer_and_unrenderable_without_a_job(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _import_csv(
        api_client,
        provisioned_org,
        stored_files,
        year_end_id=year_end_id,
        name="tiny.csv",
        content=_TINY.encode(),
        file_key="week11-closed-file",
        version_key="week11-closed-version",
        process=False,
    )
    headers = auth_headers(provisioned_org["token"])
    refused = await api_client.post(
        _docx_path(year_end_id, version_id),
        headers={**headers, "Idempotency-Key": "week11-closed"},
    )
    assert refused.status_code == 400, refused.text
    assert refused.json()["detail"] == _NOT_RENDERABLE
    with SyncSessionLocal() as session:
        count = session.execute(
            text("SELECT count(*) FROM findraft_render_jobs WHERE org_id = :oid"),
            {"oid": str(provisioned_org["org_id"])},
        ).scalar_one()
    assert count == 0

    user_id, clerk_user_id, _issued = _add_org_user(
        org_id=provisioned_org["org_id"],
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="member",
        email_prefix="week11-viewer",
    )
    token = make_access_token(
        clerk_user_id=clerk_user_id,
        clerk_org_id=provisioned_org["clerk_org_id"],
        role="owner",
        org_uuid=provisioned_org["org_id"],
    )
    _set_role(org_id=provisioned_org["org_id"], user_id=user_id, role="viewer")
    viewer = await api_client.post(
        _docx_path(year_end_id, version_id),
        headers={**auth_headers(token), "Idempotency-Key": "week11-viewer"},
    )
    assert viewer.status_code == 403
    assert viewer.json()["detail"] == _FORBIDDEN


@pytest.mark.asyncio
async def test_render_timeout_marks_the_job_failed(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    headers = auth_headers(provisioned_org["token"])
    created = await api_client.post(
        _docx_path(year_end_id, version_id),
        headers={**headers, "Idempotency-Key": "week11-timeout"},
    )
    assert created.status_code == 202, created.text

    def _timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="docx", timeout=20)

    monkeypatch.setattr("app.services.render_jobs.subprocess.run", _timeout)
    processed = _process(
        provisioned_org["org_id"], created.json()["job_id"], stored_files
    )
    assert processed is not None
    assert processed.status == "failed"
    assert processed.error_message == "DOCX render timed out"


@pytest.mark.asyncio
async def test_final_docx_reads_the_snapshot(
    api_client: AsyncClient,
    provisioned_org: dict,
    stored_files: LocalPracticeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    year_end_id = await _year_end(api_client, provisioned_org)
    version_id = await _ready_golden(
        api_client, provisioned_org, stored_files, year_end_id
    )
    headers = auth_headers(provisioned_org["token"])
    with SyncSessionLocal() as session:
        original = session.execute(
            text("SELECT name FROM companies WHERE id = :id"),
            {"id": str(provisioned_org["company_id"])},
        ).scalar_one()
        session.execute(
            text("UPDATE companies SET industry = :industry WHERE id = :id"),
            {"industry": "Widgets", "id": str(provisioned_org["company_id"])},
        )
        session.commit()
    version = await api_client.get(
        f"/year-ends/{year_end_id}/trial-balance-versions/{version_id}",
        headers=headers,
    )
    assert version.status_code == 200, version.text
    draft_id = version.json()["draft_id"]
    row_version = await _answer_disclosures(
        api_client, headers, year_end_id, draft_id, 1
    )
    finalised = await api_client.post(
        _draft_path(year_end_id, draft_id, "finalise"),
        headers={**headers, "Idempotency-Key": "week11-final"},
        json={"row_version": row_version},
    )
    assert finalised.status_code == 200, finalised.text
    with SyncSessionLocal() as session:
        session.execute(
            text(
                "UPDATE companies SET name = :name, industry = :industry "
                "WHERE id = :id"
            ),
            {
                "name": "Renamed After Final Limited",
                "industry": "Should Not Appear",
                "id": str(provisioned_org["company_id"]),
            },
        )
        session.commit()

    async def _boom(*_args, **_kwargs):
        raise AssertionError("FINAL docx recomputed the statements")

    monkeypatch.setattr("app.services.render_jobs.statements_for_version", _boom)
    created = await api_client.post(
        _docx_path(year_end_id, version_id),
        headers={**headers, "Idempotency-Key": "week11-final-docx"},
    )
    assert created.status_code == 202, created.text
    processed = _process(
        provisioned_org["org_id"], created.json()["job_id"], stored_files
    )
    assert processed is not None
    assert processed.status == "ready"
    assert processed.watermark == "FINAL"
    download = await api_client.get(
        f"{_job_path(year_end_id, version_id, created.json()['job_id'])}/download",
        headers=headers,
    )
    assert download.status_code == 200, download.text
    assert "statutory-statements-final.docx" in download.headers["content-disposition"]
    xml = _xml(download.content)
    assert original in xml
    assert "Widgets" in xml
    assert "Renamed After Final Limited" not in xml
    assert "Should Not Appear" not in xml
    frozen = await api_client.get(
        _statements_path(year_end_id, version_id), headers=headers
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["watermark"] == "FINAL"
    headings = [page["heading"] for page in frozen.json()["pages"]]
    assert headings[0] == "Compilation report"
    assert "auditor" not in " ".join(headings).casefold()
