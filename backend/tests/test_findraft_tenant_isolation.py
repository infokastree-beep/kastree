"""Product 2 tenant isolation.

The local login is `findraft`, a superuser, which bypasses RLS even with
FORCE. RLS tests call SET ROLE findraft_app and then assert that current_user
is that role and that rolsuper and rolbypassrls are both false. session_user
stays `findraft` because SET ROLE does not change the login. The foreign-key,
re-pin, and org-id trigger tests run as the superuser login; those constraints
apply to table owners and do not depend on RLS.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.db import SyncSessionLocal, set_rls_org_id
from app.models.client import Client
from app.models.company import Company
from app.services.org_provisioning import provision_first_signup
from findraft.models.adjustments import (
    AdjustmentJournal,
    AdjustmentLine,
    DisclosureAnswer,
    DraftOperation,
)
from findraft.models.draft_version import DraftVersion
from findraft.models.year_end import YearEnd


def _delete_org(org_id: uuid.UUID) -> None:
    with SyncSessionLocal() as session:
        session.execute(text("RESET ROLE"))
        set_rls_org_id(session, org_id)
        oid = str(org_id)
        session.execute(
            text(
                "ALTER TABLE findraft_prior_year_lines "
                "DISABLE TRIGGER findraft_prior_year_lines_locked"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_confirmed_mappings "
                "DISABLE TRIGGER findraft_confirmed_mappings_immutable"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_journals "
                "DISABLE TRIGGER findraft_adjustment_journals_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "DISABLE TRIGGER findraft_adjustment_lines_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "DISABLE TRIGGER findraft_adjustment_journal_must_balance"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_disclosure_answers "
                "DISABLE TRIGGER findraft_disclosure_answers_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE audit_logs DISABLE TRIGGER findraft_audit_log_append_only"
            )
        )
        session.execute(
            text("DELETE FROM audit_logs WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_render_jobs WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_draft_operations WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_adjustment_lines WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_adjustment_journals WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_disclosure_answers WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_confirmed_mappings WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_fa_lines WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_fa_versions WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_tb_lines WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_draft_versions WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_tb_versions WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_prior_year_lines WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text(
                "ALTER TABLE findraft_confirmed_mappings "
                "ENABLE TRIGGER findraft_confirmed_mappings_immutable"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_prior_year_lines "
                "ENABLE TRIGGER findraft_prior_year_lines_locked"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_journals "
                "ENABLE TRIGGER findraft_adjustment_journals_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "ENABLE TRIGGER findraft_adjustment_lines_locked_draft"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_adjustment_lines "
                "ENABLE TRIGGER findraft_adjustment_journal_must_balance"
            )
        )
        session.execute(
            text(
                "ALTER TABLE findraft_disclosure_answers "
                "ENABLE TRIGGER findraft_disclosure_answers_locked_draft"
            )
        )
        session.execute(
            text("DELETE FROM findraft_source_documents WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_draft_versions WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM findraft_year_ends WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text(
                "DELETE FROM companies WHERE client_id IN "
                "(SELECT id FROM clients WHERE org_id = :oid)"
            ),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM clients WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM notifications WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM users WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM subscription_events WHERE org_id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("DELETE FROM organisations WHERE id = :oid"),
            {"oid": oid},
        )
        session.execute(
            text("ALTER TABLE audit_logs ENABLE TRIGGER findraft_audit_log_append_only")
        )
        session.commit()


def _provision(suffix: str) -> dict:
    with SyncSessionLocal() as session:
        provisioned = provision_first_signup(
            session,
            clerk_org_id=f"org_fd_{suffix}",
            org_name=f"FinDraft {suffix}",
            clerk_user_id=f"user_fd_{suffix}",
            email=f"fd-{suffix}@example.com",
            role="owner",
        )
        set_rls_org_id(session, provisioned.organisation.id)
        client = Client(org_id=provisioned.organisation.id, name=f"Client {suffix}")
        session.add(client)
        session.flush()
        company = Company(
            client_id=client.id,
            name=f"Company {suffix}",
            functional_currency="EUR",
        )
        session.add(company)
        session.flush()
        session.refresh(company)
        year_end = YearEnd(
            org_id=company.org_id,
            company_id=company.id,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            pack_id="frs102-1a-ie",
            pack_version="2024.09",
        )
        session.add(year_end)
        session.flush()
        draft = DraftVersion(
            org_id=company.org_id,
            company_id=company.id,
            year_end_id=year_end.id,
            version_number=1,
            pack_id=year_end.pack_id,
            pack_version=year_end.pack_version,
        )
        session.add(draft)
        session.flush()
        journal = AdjustmentJournal(
            org_id=company.org_id,
            company_id=company.id,
            draft_version_id=draft.id,
            narration=f"Reclass {suffix}",
        )
        session.add(journal)
        session.flush()
        session.add(
            AdjustmentLine(
                org_id=company.org_id,
                company_id=company.id,
                journal_id=journal.id,
                draft_version_id=draft.id,
                line_no=1,
                nominal_code="2110",
                account_name="Other debtors",
                canonical_line="OTHER_DEBTORS",
                debit=Decimal("10.00"),
                credit=Decimal("0.00"),
            )
        )
        session.add(
            AdjustmentLine(
                org_id=company.org_id,
                company_id=company.id,
                journal_id=journal.id,
                draft_version_id=draft.id,
                line_no=2,
                nominal_code="2130",
                account_name="Bank current account",
                canonical_line="CASH",
                debit=Decimal("0.00"),
                credit=Decimal("10.00"),
            )
        )
        session.add(
            DisclosureAnswer(
                org_id=company.org_id,
                company_id=company.id,
                draft_version_id=draft.id,
                flag_name="GOODWILL",
                answer=False,
            )
        )
        session.add(
            DraftOperation(
                org_id=company.org_id,
                company_id=company.id,
                draft_version_id=draft.id,
                action="adjust",
                idempotency_key=f"iso-{suffix}",
                request_sha256="a" * 64,
                response={"ok": True},
            )
        )
        session.commit()
        return {
            "org_id": provisioned.organisation.id,
            "company_id": company.id,
            "year_end_id": year_end.id,
            "draft_id": draft.id,
        }


@pytest.fixture
def two_practices() -> Iterator[tuple[dict, dict]]:
    suffix = uuid.uuid4().hex[:8]
    first = _provision(f"a{suffix}")
    second = _provision(f"b{suffix}")
    try:
        yield first, second
    finally:
        _delete_org(first["org_id"])
        _delete_org(second["org_id"])


def _role_snapshot(session):
    return session.execute(
        text(
            """
            SELECT session_user AS login_role,
                   current_user AS executing_role,
                   r.rolsuper,
                   r.rolbypassrls
            FROM pg_roles AS r
            WHERE r.rolname = current_user
            """
        )
    ).one()


def _as_app_role(session) -> None:
    session.execute(text("SET ROLE findraft_app"))
    row = _role_snapshot(session)
    assert row.login_role == "findraft"
    assert row.executing_role == "findraft_app"
    assert row.rolsuper is False
    assert row.rolbypassrls is False
    print(
        f"executing_role={row.executing_role} login_role={row.login_role} "
        f"rolsuper={row.rolsuper} rolbypassrls={row.rolbypassrls}",
        flush=True,
    )


def _as_login_superuser(session) -> None:
    row = _role_snapshot(session)
    assert row.login_role == "findraft"
    assert row.executing_role == "findraft"
    assert row.rolsuper is True
    print(
        f"executing_role={row.executing_role} login_role={row.login_role} "
        f"rolsuper={row.rolsuper} rolbypassrls={row.rolbypassrls}",
        flush=True,
    )


def _insert_render_job(
    session, practice: dict, version_id: uuid.UUID, *, suffix: str
) -> uuid.UUID:
    job_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO findraft_render_jobs (
              id, org_id, company_id, tb_version_id, format, status,
              idempotency_key, watermark
            ) VALUES (
              :id, :org, :company, :version, 'docx', 'pending',
              :idem, 'DRAFT'
            )
            """
        ),
        {
            "id": str(job_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "version": str(version_id),
            "idem": f"docx-{suffix}",
        },
    )
    return job_id


def test_render_job_unset_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            first_version = _insert_source_and_version(session, first, suffix="rj-a")
            second_version = _insert_source_and_version(session, second, suffix="rj-b")
            _insert_render_job(session, first, first_version, suffix="a")
            _insert_render_job(session, second, second_version, suffix="b")
            _as_app_role(session)
            count = session.execute(
                text("SELECT count(*) FROM findraft_render_jobs")
            ).scalar_one()
            assert count == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_render_job_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            own_version = _insert_source_and_version(session, first, suffix="rj-own")
            other_version = _insert_source_and_version(
                session, second, suffix="rj-other"
            )
            own_id = _insert_render_job(session, first, own_version, suffix="own")
            other_id = _insert_render_job(
                session, second, other_version, suffix="other"
            )
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            seen = (
                session.execute(text("SELECT id FROM findraft_render_jobs"))
                .scalars()
                .all()
            )
            assert seen == [own_id]
            assert other_id not in seen
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_render_job_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            version_id = _insert_source_and_version(session, second, suffix="rj-cross")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                _insert_render_job(session, second, version_id, suffix="cross")
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


_GENESIS = "0" * 64


def _insert_audit_row(
    session,
    practice: dict,
    *,
    chain_seq: int,
    prev_hash: str,
    row_hash: str,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO audit_logs (
              id, org_id, action, entity_type, entity_id,
              chain_seq, prev_hash, row_hash
            ) VALUES (
              :id, :org, 'recorded', 'client', :entity,
              :seq, :prev, :row_hash
            )
            """
        ),
        {
            "id": str(row_id),
            "org": str(practice["org_id"]),
            "entity": str(practice["company_id"]),
            "seq": chain_seq,
            "prev": prev_hash,
            "row_hash": row_hash,
        },
    )
    return row_id


def test_audit_log_unset_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            _insert_audit_row(
                session,
                first,
                chain_seq=1,
                prev_hash=_GENESIS,
                row_hash="a" * 64,
            )
            _insert_audit_row(
                session,
                second,
                chain_seq=1,
                prev_hash=_GENESIS,
                row_hash="b" * 64,
            )
            _as_app_role(session)
            count = session.execute(
                text("SELECT count(*) FROM audit_logs")
            ).scalar_one()
            assert count == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_audit_log_app_role_cannot_update_or_delete(
    two_practices: tuple[dict, dict],
) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            row_id = _insert_audit_row(
                session,
                first,
                chain_seq=1,
                prev_hash=_GENESIS,
                row_hash="c" * 64,
            )
            with pytest.raises(DBAPIError, match="permission denied"):
                session.execute(
                    text("UPDATE audit_logs SET action = 'tamper' WHERE id = :id"),
                    {"id": str(row_id)},
                )
            session.rollback()
            session.execute(text("SET ROLE findraft_app"))
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            row_id = _insert_audit_row(
                session,
                first,
                chain_seq=1,
                prev_hash=_GENESIS,
                row_hash="c" * 64,
            )
            with pytest.raises(DBAPIError, match="permission denied"):
                session.execute(
                    text("DELETE FROM audit_logs WHERE id = :id"),
                    {"id": str(row_id)},
                )
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_audit_log_trigger_refuses_owner_update(
    two_practices: tuple[dict, dict],
) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        row_id = _insert_audit_row(
            session,
            first,
            chain_seq=1,
            prev_hash=_GENESIS,
            row_hash="d" * 64,
        )
        with pytest.raises(DBAPIError, match="audit log is append-only"):
            session.execute(
                text("UPDATE audit_logs SET action = 'tamper' WHERE id = :id"),
                {"id": str(row_id)},
            )
        session.rollback()


def test_audit_log_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                _insert_audit_row(
                    session,
                    second,
                    chain_seq=1,
                    prev_hash=_GENESIS,
                    row_hash="e" * 64,
                )
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_company_org_id_is_copied_from_client(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        row = session.execute(
            text("SELECT org_id FROM companies WHERE id = :id"),
            {"id": str(first["company_id"])},
        ).one()
        assert row.org_id == first["org_id"]


def test_unset_tenant_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            year_ends = session.execute(
                text("SELECT count(*) FROM findraft_year_ends")
            ).scalar_one()
            drafts = session.execute(
                text("SELECT count(*) FROM findraft_draft_versions")
            ).scalar_one()
            journals = session.execute(
                text("SELECT count(*) FROM findraft_adjustment_journals")
            ).scalar_one()
            lines = session.execute(
                text("SELECT count(*) FROM findraft_adjustment_lines")
            ).scalar_one()
            answers = session.execute(
                text("SELECT count(*) FROM findraft_disclosure_answers")
            ).scalar_one()
            operations = session.execute(
                text("SELECT count(*) FROM findraft_draft_operations")
            ).scalar_one()
            assert year_ends == 0
            assert drafts == 0
            assert journals == 0
            assert lines == 0
            assert answers == 0
            assert operations == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            year_ids = (
                session.execute(text("SELECT id FROM findraft_year_ends"))
                .scalars()
                .all()
            )
            draft_ids = (
                session.execute(text("SELECT id FROM findraft_draft_versions"))
                .scalars()
                .all()
            )
            journal_orgs = (
                session.execute(text("SELECT org_id FROM findraft_adjustment_journals"))
                .scalars()
                .all()
            )
            line_count = session.execute(
                text("SELECT count(*) FROM findraft_adjustment_lines")
            ).scalar_one()
            answer_orgs = (
                session.execute(text("SELECT org_id FROM findraft_disclosure_answers"))
                .scalars()
                .all()
            )
            operation_orgs = (
                session.execute(text("SELECT org_id FROM findraft_draft_operations"))
                .scalars()
                .all()
            )
            assert year_ids == [first["year_end_id"]]
            assert draft_ids == [first["draft_id"]]
            assert journal_orgs == [first["org_id"]]
            assert line_count == 2
            assert answer_orgs == [first["org_id"]]
            assert operation_orgs == [first["org_id"]]
            assert second["year_end_id"] not in year_ids
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_year_ends (
                          id, org_id, company_id, period_end, pack_id, pack_version
                        ) VALUES (
                          :id, :org, :company, DATE '2025-12-31',
                          'frs102-1a-ie', '2024.09'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(second["org_id"]),
                        "company": str(second["company_id"]),
                    },
                )
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_with_check_rejects_cross_tenant_adjustment(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_adjustment_journals (
                          id, org_id, company_id, draft_version_id, narration
                        ) VALUES (
                          :id, :org, :company, :draft, 'cross'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(second["org_id"]),
                        "company": str(second["company_id"]),
                        "draft": str(second["draft_id"]),
                    },
                )
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_unbalanced_adjustment_is_refused_at_commit(
    two_practices: tuple[dict, dict],
) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        journal_id = uuid.uuid4()
        session.execute(
            text(
                """
                INSERT INTO findraft_adjustment_journals (
                  id, org_id, company_id, draft_version_id, narration
                ) VALUES (:id, :org, :company, :draft, 'one sided')
                """
            ),
            {
                "id": str(journal_id),
                "org": str(first["org_id"]),
                "company": str(first["company_id"]),
                "draft": str(first["draft_id"]),
            },
        )
        session.execute(
            text(
                """
                INSERT INTO findraft_adjustment_lines (
                  id, org_id, company_id, journal_id, draft_version_id, line_no,
                  nominal_code, account_name, canonical_line, debit, credit
                ) VALUES (
                  :id, :org, :company, :journal, :draft, 1,
                  '2110', 'Other debtors', 'OTHER_DEBTORS', 10.00, 0
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "org": str(first["org_id"]),
                "company": str(first["company_id"]),
                "journal": str(journal_id),
                "draft": str(first["draft_id"]),
            },
        )
        with pytest.raises(DBAPIError, match="does not balance"):
            session.commit()
        session.rollback()


def test_locked_draft_refuses_child_writes(
    two_practices: tuple[dict, dict],
) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        session.execute(
            text(
                "UPDATE findraft_draft_versions SET status = 'locked' " "WHERE id = :id"
            ),
            {"id": str(first["draft_id"])},
        )
        session.commit()
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(DBAPIError, match="writes are refused"):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_disclosure_answers (
                      id, org_id, company_id, draft_version_id, flag_name, answer
                    ) VALUES (
                      :id, :org, :company, :draft, 'HAS_EMPLOYEES', false
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(first["org_id"]),
                    "company": str(first["company_id"]),
                    "draft": str(first["draft_id"]),
                },
            )
            session.commit()
        session.rollback()


def test_final_snapshot_is_immutable(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    digest = "b" * 64
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        session.execute(
            text(
                """
                UPDATE findraft_draft_versions
                SET status = 'final',
                    snapshot = CAST(:snapshot AS jsonb),
                    inputs_sha256 = :digest,
                    engine_sha = :digest
                WHERE id = :id
                """
            ),
            {
                "id": str(first["draft_id"]),
                "snapshot": '{"watermark": "FINAL"}',
                "digest": digest,
            },
        )
        session.commit()
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(DBAPIError, match="FINAL draft is immutable"):
            session.execute(
                text(
                    """
                    UPDATE findraft_draft_versions
                    SET snapshot = CAST('{"watermark": "CHANGED"}' AS jsonb)
                    WHERE id = :id
                    """
                ),
                {"id": str(first["draft_id"])},
            )
            session.commit()
        session.rollback()


def test_composite_fk_rejects_mismatched_company(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_year_ends (
                      id, org_id, company_id, period_end, pack_id, pack_version
                    ) VALUES (
                      :id, :org, :company, DATE '2025-12-31',
                      'frs102-1a-ie', '2024.09'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(first["org_id"]),
                    "company": str(second["company_id"]),
                },
            )
        session.rollback()


def test_repin_is_rejected(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(DBAPIError, match="already pinned"):
            session.execute(
                text(
                    """
                    UPDATE findraft_year_ends
                    SET pack_version = '2025.01'
                    WHERE id = :id
                    """
                ),
                {"id": str(first["year_end_id"])},
            )
        session.rollback()


def _insert_document(session, practice: dict, *, suffix: str) -> uuid.UUID:
    document_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO findraft_source_documents (
              id, org_id, company_id, storage_key, original_filename,
              detected_type, byte_size, sha256, idempotency_key
            ) VALUES (
              :id, :org, :company, :key, 'notes.pdf',
              'pdf', 12, :sha, :idem
            )
            """
        ),
        {
            "id": str(document_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "key": f"practices/{practice['org_id']}/companies/{practice['company_id']}/documents/{document_id}",
            "sha": "ab" * 32,
            "idem": f"idem-{suffix}",
        },
    )
    return document_id


def test_source_document_unset_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            _insert_document(session, first, suffix="a")
            _insert_document(session, second, suffix="b")
            _as_app_role(session)
            count = session.execute(
                text("SELECT count(*) FROM findraft_source_documents")
            ).scalar_one()
            assert count == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_source_document_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            own_id = _insert_document(session, first, suffix="own")
            other_id = _insert_document(session, second, suffix="other")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            seen = (
                session.execute(text("SELECT id FROM findraft_source_documents"))
                .scalars()
                .all()
            )
            assert seen == [own_id]
            assert other_id not in seen
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_source_document_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                _insert_document(session, second, suffix="cross")
            session.rollback()
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_source_document_composite_fk_rejects_mismatched_company(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        mixed = dict(second)
        mixed["org_id"] = first["org_id"]
        with pytest.raises(IntegrityError):
            _insert_document(session, mixed, suffix="fk")
        session.rollback()


def _insert_source_and_version(session, practice: dict, *, suffix: str) -> uuid.UUID:
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO findraft_source_documents (
              id, org_id, company_id, storage_key, original_filename,
              detected_type, byte_size, sha256, idempotency_key
            ) VALUES (
              :id, :org, :company, :key, 'tb.csv',
              'csv', 8, :sha, :idem
            )
            """
        ),
        {
            "id": str(document_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "key": (
                f"practices/{practice['org_id']}/companies/"
                f"{practice['company_id']}/documents/{document_id}"
            ),
            "sha": "cd" * 32,
            "idem": f"src-{suffix}",
        },
    )
    session.execute(
        text(
            """
            INSERT INTO findraft_tb_versions (
              id, org_id, company_id, year_end_id, version_number,
              source_document_id, status, idempotency_key
            ) VALUES (
              :id, :org, :company, :year_end, 1,
              :document, 'pending', :idem
            )
            """
        ),
        {
            "id": str(version_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "year_end": str(practice["year_end_id"]),
            "document": str(document_id),
            "idem": f"tb-{suffix}",
        },
    )
    session.execute(
        text(
            """
            INSERT INTO findraft_tb_lines (
              id, org_id, company_id, tb_version_id, line_no,
              nominal_code, account_name, debit, credit
            ) VALUES (
              :id, :org, :company, :version, 1,
              '1000', 'Cash', 10.00, 10.00
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "version": str(version_id),
        },
    )
    session.execute(
        text(
            """
            INSERT INTO findraft_prior_year_lines (
              id, org_id, company_id, year_end_id, canonical_line, amount
            ) VALUES (
              :id, :org, :company, :year_end, 'CASH', 10.00
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "year_end": str(practice["year_end_id"]),
        },
    )
    return version_id


def test_tb_version_unset_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            _insert_source_and_version(session, first, suffix="a")
            _insert_source_and_version(session, second, suffix="b")
            _as_app_role(session)
            versions = session.execute(
                text("SELECT count(*) FROM findraft_tb_versions")
            ).scalar_one()
            lines = session.execute(
                text("SELECT count(*) FROM findraft_tb_lines")
            ).scalar_one()
            prior = session.execute(
                text("SELECT count(*) FROM findraft_prior_year_lines")
            ).scalar_one()
            assert versions == 0
            assert lines == 0
            assert prior == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_tb_version_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            own_id = _insert_source_and_version(session, first, suffix="own")
            other_id = _insert_source_and_version(session, second, suffix="other")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            seen = (
                session.execute(text("SELECT id FROM findraft_tb_versions"))
                .scalars()
                .all()
            )
            line_versions = (
                session.execute(text("SELECT tb_version_id FROM findraft_tb_lines"))
                .scalars()
                .all()
            )
            prior_ends = (
                session.execute(
                    text("SELECT year_end_id FROM findraft_prior_year_lines")
                )
                .scalars()
                .all()
            )
            assert seen == [own_id]
            assert other_id not in seen
            assert line_versions == [own_id]
            assert prior_ends == [first["year_end_id"]]
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def _version_parent(session, version_id: uuid.UUID):
    return session.execute(
        text(
            """
            SELECT org_id, company_id, year_end_id, source_document_id
            FROM findraft_tb_versions WHERE id = :id
            """
        ),
        {"id": str(version_id)},
    ).one()


def test_tb_version_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            version_id = _insert_source_and_version(session, second, suffix="base")
            parent = _version_parent(session, version_id)
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_tb_versions (
                          id, org_id, company_id, year_end_id, version_number,
                          source_document_id, status, idempotency_key
                        ) VALUES (
                          :id, :org, :company, :year_end, 2,
                          :document, 'pending', 'tb-cross'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(parent.org_id),
                        "company": str(parent.company_id),
                        "year_end": str(parent.year_end_id),
                        "document": str(parent.source_document_id),
                    },
                )
            session.rollback()
            session.execute(text("RESET ROLE"))
            _as_login_superuser(session)
            version_id = _insert_source_and_version(session, second, suffix="lines")
            parent = _version_parent(session, version_id)
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_tb_lines (
                          id, org_id, company_id, tb_version_id, line_no,
                          nominal_code, account_name, debit, credit
                        ) VALUES (
                          :id, :org, :company, :version, 2,
                          '1000', 'Cash', 1.00, 1.00
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(parent.org_id),
                        "company": str(parent.company_id),
                        "version": str(version_id),
                    },
                )
            session.rollback()
            session.execute(text("RESET ROLE"))
            _as_login_superuser(session)
            _insert_source_and_version(session, second, suffix="prior")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_prior_year_lines (
                          id, org_id, company_id, year_end_id, canonical_line, amount
                        ) VALUES (
                          :id, :org, :company, :year_end, 'REVENUE', 1.00
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(second["org_id"]),
                        "company": str(second["company_id"]),
                        "year_end": str(second["year_end_id"]),
                    },
                )
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_tb_version_composite_fk_rejects_mismatched_company(
    two_practices: tuple[dict, dict],
) -> None:
    """The year-end foreign key is (year_end_id, org_id, company_id).

    A version for practice B that points at practice A's year end fails that
    constraint. The source document and company pair stay valid, so the failure
    is the version foreign key.
    """
    first, second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        version_id = _insert_source_and_version(session, second, suffix="fk")
        parent = _version_parent(session, version_id)
        with pytest.raises(IntegrityError, match="findraft_tb_versions_year_end_fk"):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_tb_versions (
                      id, org_id, company_id, year_end_id, version_number,
                      source_document_id, status, idempotency_key
                    ) VALUES (
                      :id, :org, :company, :year_end, 2,
                      :document, 'pending', 'tb-fk-mismatch'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(parent.org_id),
                    "company": str(parent.company_id),
                    "year_end": str(first["year_end_id"]),
                    "document": str(parent.source_document_id),
                },
            )
        session.rollback()


def _insert_fa_version(session, practice: dict, *, suffix: str) -> uuid.UUID:
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO findraft_source_documents (
              id, org_id, company_id, storage_key, original_filename,
              detected_type, byte_size, sha256, idempotency_key
            ) VALUES (
              :id, :org, :company, :key, 'fa.csv',
              'csv', 8, :sha, :idem
            )
            """
        ),
        {
            "id": str(document_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "key": (
                f"practices/{practice['org_id']}/companies/"
                f"{practice['company_id']}/documents/{document_id}"
            ),
            "sha": "fa" * 32,
            "idem": f"fa-src-{suffix}",
        },
    )
    session.execute(
        text(
            """
            INSERT INTO findraft_fa_versions (
              id, org_id, company_id, year_end_id, version_number,
              source_document_id, status, idempotency_key
            ) VALUES (
              :id, :org, :company, :year_end, 1,
              :document, 'pending', :idem
            )
            """
        ),
        {
            "id": str(version_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "year_end": str(practice["year_end_id"]),
            "document": str(document_id),
            "idem": f"fa-{suffix}",
        },
    )
    session.execute(
        text(
            """
            INSERT INTO findraft_fa_lines (
              id, org_id, company_id, fa_version_id, line_no, asset_class,
              opening_cost, additions, disposals, disposals_dep, opening_dep, charge
            ) VALUES (
              :id, :org, :company, :version, 1, 'Plant',
              10.00, 0.00, 0.00, 0.00, 0.00, 0.00
            )
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "version": str(version_id),
        },
    )
    return version_id


def test_fa_version_unset_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            _insert_fa_version(session, first, suffix="a")
            _insert_fa_version(session, second, suffix="b")
            _as_app_role(session)
            versions = session.execute(
                text("SELECT count(*) FROM findraft_fa_versions")
            ).scalar_one()
            lines = session.execute(
                text("SELECT count(*) FROM findraft_fa_lines")
            ).scalar_one()
            assert versions == 0
            assert lines == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_fa_version_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            own_id = _insert_fa_version(session, first, suffix="own")
            other_id = _insert_fa_version(session, second, suffix="other")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            seen = (
                session.execute(text("SELECT id FROM findraft_fa_versions"))
                .scalars()
                .all()
            )
            line_versions = (
                session.execute(text("SELECT fa_version_id FROM findraft_fa_lines"))
                .scalars()
                .all()
            )
            assert seen == [own_id]
            assert other_id not in seen
            assert line_versions == [own_id]
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_fa_version_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            version_id = _insert_fa_version(session, second, suffix="base")
            parent = session.execute(
                text(
                    """
                    SELECT org_id, company_id, year_end_id, source_document_id
                    FROM findraft_fa_versions WHERE id = :id
                    """
                ),
                {"id": str(version_id)},
            ).one()
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_fa_versions (
                          id, org_id, company_id, year_end_id, version_number,
                          source_document_id, status, idempotency_key
                        ) VALUES (
                          :id, :org, :company, :year_end, 2,
                          :document, 'pending', 'fa-cross'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(parent.org_id),
                        "company": str(parent.company_id),
                        "year_end": str(parent.year_end_id),
                        "document": str(parent.source_document_id),
                    },
                )
            session.rollback()
            session.execute(text("RESET ROLE"))
            _as_login_superuser(session)
            version_id = _insert_fa_version(session, second, suffix="lines")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_fa_lines (
                          id, org_id, company_id, fa_version_id, line_no, asset_class,
                          opening_cost, additions, disposals, disposals_dep,
                          opening_dep, charge
                        ) VALUES (
                          :id, :org, :company, :version, 2, 'Other',
                          1.00, 0.00, 0.00, 0.00, 0.00, 0.00
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(second["org_id"]),
                        "company": str(second["company_id"]),
                        "version": str(version_id),
                    },
                )
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_fa_version_composite_fk_rejects_mismatched_year_end(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        version_id = _insert_fa_version(session, second, suffix="fk")
        parent = session.execute(
            text(
                """
                SELECT org_id, company_id, source_document_id
                FROM findraft_fa_versions WHERE id = :id
                """
            ),
            {"id": str(version_id)},
        ).one()
        with pytest.raises(IntegrityError, match="findraft_fa_versions_year_end_fk"):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_fa_versions (
                      id, org_id, company_id, year_end_id, version_number,
                      source_document_id, status, idempotency_key
                    ) VALUES (
                      :id, :org, :company, :year_end, 2,
                      :document, 'pending', 'fa-fk-mismatch'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(parent.org_id),
                    "company": str(parent.company_id),
                    "year_end": str(first["year_end_id"]),
                    "document": str(parent.source_document_id),
                },
            )
        session.rollback()


def test_draft_pack_must_match_year_end(two_practices: tuple[dict, dict]) -> None:
    first, _second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        with pytest.raises(IntegrityError):
            session.add(
                DraftVersion(
                    org_id=first["org_id"],
                    company_id=first["company_id"],
                    year_end_id=first["year_end_id"],
                    version_number=2,
                    pack_id="frs102-1a-ie",
                    pack_version="2025.01",
                )
            )
            session.commit()
        session.rollback()


def _insert_confirmed_mapping(session, practice: dict, *, suffix: str) -> uuid.UUID:
    version_id = _insert_source_and_version(session, practice, suffix=suffix)
    mapping_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO findraft_confirmed_mappings (
              id, org_id, company_id, tb_version_id, nominal_code, canonical_line
            ) VALUES (
              :id, :org, :company, :version, '4000', 'REVENUE'
            )
            """
        ),
        {
            "id": str(mapping_id),
            "org": str(practice["org_id"]),
            "company": str(practice["company_id"]),
            "version": str(version_id),
        },
    )
    return mapping_id


def test_confirmed_mapping_unset_context_returns_no_rows(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            _insert_confirmed_mapping(session, first, suffix="map-a")
            _insert_confirmed_mapping(session, second, suffix="map-b")
            _as_app_role(session)
            count = session.execute(
                text("SELECT count(*) FROM findraft_confirmed_mappings")
            ).scalar_one()
            assert count == 0
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_confirmed_mapping_app_role_sees_only_its_practice(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            own_id = _insert_confirmed_mapping(session, first, suffix="map-own")
            other_id = _insert_confirmed_mapping(session, second, suffix="map-other")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            seen = (
                session.execute(text("SELECT id FROM findraft_confirmed_mappings"))
                .scalars()
                .all()
            )
            assert seen == [own_id]
            assert other_id not in seen
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_confirmed_mapping_with_check_rejects_cross_tenant_insert(
    two_practices: tuple[dict, dict],
) -> None:
    first, second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            version_id = _insert_source_and_version(session, second, suffix="map-base")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="row-level security"):
                session.execute(
                    text(
                        """
                        INSERT INTO findraft_confirmed_mappings (
                          id, org_id, company_id, tb_version_id,
                          nominal_code, canonical_line
                        ) VALUES (
                          :id, :org, :company, :version, '4000', 'REVENUE'
                        )
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org": str(second["org_id"]),
                        "company": str(second["company_id"]),
                        "version": str(version_id),
                    },
                )
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_confirmed_mapping_is_immutable(two_practices: tuple[dict, dict]) -> None:
    """The trigger runs as the table owner. The app role has no UPDATE grant."""
    first, _second = two_practices
    with SyncSessionLocal() as session:
        try:
            _as_login_superuser(session)
            mapping_id = _insert_confirmed_mapping(session, first, suffix="map-lock")
            with pytest.raises(DBAPIError, match="confirmed mapping is immutable"):
                session.execute(
                    text(
                        """
                        UPDATE findraft_confirmed_mappings
                        SET canonical_line = 'CASH'
                        WHERE id = :id
                        """
                    ),
                    {"id": str(mapping_id)},
                )
            session.rollback()
            session.execute(text("RESET ROLE"))
            _as_login_superuser(session)
            mapping_id = _insert_confirmed_mapping(session, first, suffix="map-grant")
            _as_app_role(session)
            session.execute(
                text("SELECT set_config('app.current_org_id', :org, true)"),
                {"org": str(first["org_id"])},
            )
            with pytest.raises(ProgrammingError, match="permission denied"):
                session.execute(
                    text(
                        """
                        UPDATE findraft_confirmed_mappings
                        SET canonical_line = 'CASH'
                        WHERE id = :id
                        """
                    ),
                    {"id": str(mapping_id)},
                )
        finally:
            session.rollback()
            session.execute(text("RESET ROLE"))


def test_confirmed_mapping_composite_fk_rejects_mismatched_company(
    two_practices: tuple[dict, dict],
) -> None:
    """The company pair is valid. The version belongs to the other practice."""
    first, second = two_practices
    with SyncSessionLocal() as session:
        _as_login_superuser(session)
        version_id = _insert_source_and_version(session, first, suffix="map-fk")
        with pytest.raises(
            IntegrityError, match="findraft_confirmed_mappings_version_fk"
        ):
            session.execute(
                text(
                    """
                    INSERT INTO findraft_confirmed_mappings (
                      id, org_id, company_id, tb_version_id,
                      nominal_code, canonical_line
                    ) VALUES (
                      :id, :org, :company, :version, '4000', 'REVENUE'
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org": str(second["org_id"]),
                    "company": str(second["company_id"]),
                    "version": str(version_id),
                },
            )
        session.rollback()
