"""Week 10 draft inputs: balanced adjustment journals and disclosure answers.

These are not a journal parser and not note-override or text-block tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdjustmentJournal(Base):
    __tablename__ = "findraft_adjustment_journals"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "org_id",
            "company_id",
            name="findraft_adjustment_journals_id_org_company_key",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_adjustment_journals_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["draft_version_id", "org_id", "company_id"],
            [
                "findraft_draft_versions.id",
                "findraft_draft_versions.org_id",
                "findraft_draft_versions.company_id",
            ],
            name="findraft_adjustment_journals_draft_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_adjustment_journals_org_id", "org_id"),
        Index("idx_findraft_adjustment_journals_draft_id", "draft_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    narration: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AdjustmentLine(Base):
    __tablename__ = "findraft_adjustment_lines"
    __table_args__ = (
        UniqueConstraint(
            "journal_id",
            "line_no",
            name="findraft_adjustment_lines_number_key",
        ),
        ForeignKeyConstraint(
            ["journal_id", "org_id", "company_id"],
            [
                "findraft_adjustment_journals.id",
                "findraft_adjustment_journals.org_id",
                "findraft_adjustment_journals.company_id",
            ],
            name="findraft_adjustment_lines_journal_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["draft_version_id", "org_id", "company_id"],
            [
                "findraft_draft_versions.id",
                "findraft_draft_versions.org_id",
                "findraft_draft_versions.company_id",
            ],
            name="findraft_adjustment_lines_draft_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "debit >= 0 AND credit >= 0",
            name="findraft_adjustment_lines_non_negative",
        ),
        CheckConstraint(
            "(debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)",
            name="findraft_adjustment_lines_one_side",
        ),
        Index("idx_findraft_adjustment_lines_org_id", "org_id"),
        Index("idx_findraft_adjustment_lines_journal_id", "journal_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_line: Mapped[str] = mapped_column(String(64), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)


class DisclosureAnswer(Base):
    __tablename__ = "findraft_disclosure_answers"
    __table_args__ = (
        UniqueConstraint(
            "draft_version_id",
            "flag_name",
            name="findraft_disclosure_answers_flag_key",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_disclosure_answers_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["draft_version_id", "org_id", "company_id"],
            [
                "findraft_draft_versions.id",
                "findraft_draft_versions.org_id",
                "findraft_draft_versions.company_id",
            ],
            name="findraft_disclosure_answers_draft_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_disclosure_answers_org_id", "org_id"),
        Index("idx_findraft_disclosure_answers_draft_id", "draft_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    flag_name: Mapped[str] = mapped_column(String(64), nullable=False)
    answer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DraftOperation(Base):
    __tablename__ = "findraft_draft_operations"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "idempotency_key",
            name="findraft_draft_operations_idempotency_key",
        ),
        ForeignKeyConstraint(
            ["draft_version_id", "org_id", "company_id"],
            [
                "findraft_draft_versions.id",
                "findraft_draft_versions.org_id",
                "findraft_draft_versions.company_id",
            ],
            name="findraft_draft_operations_draft_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_draft_operations_org_id", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
