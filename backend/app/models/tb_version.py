"""Immutable Product 2 trial-balance version and its lines."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TrialBalanceVersion(Base):
    __tablename__ = "findraft_tb_versions"
    __table_args__ = (
        UniqueConstraint(
            "year_end_id",
            "version_number",
            name="findraft_tb_versions_number_key",
        ),
        UniqueConstraint(
            "org_id",
            "idempotency_key",
            name="findraft_tb_versions_idempotency_key",
        ),
        CheckConstraint(
            "version_number >= 1", name="findraft_tb_versions_number_check"
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="findraft_tb_versions_status_check",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_tb_versions_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["year_end_id", "org_id", "company_id"],
            [
                "findraft_year_ends.id",
                "findraft_year_ends.org_id",
                "findraft_year_ends.company_id",
            ],
            name="findraft_tb_versions_year_end_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_document_id", "org_id", "company_id"],
            [
                "findraft_source_documents.id",
                "findraft_source_documents.org_id",
                "findraft_source_documents.company_id",
            ],
            name="findraft_tb_versions_source_fk",
        ),
        Index("idx_findraft_tb_versions_org_id", "org_id"),
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
    year_end_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TrialBalanceLine(Base):
    __tablename__ = "findraft_tb_lines"
    __table_args__ = (
        UniqueConstraint(
            "tb_version_id", "line_no", name="findraft_tb_lines_number_key"
        ),
        CheckConstraint("line_no >= 1", name="findraft_tb_lines_line_check"),
        CheckConstraint("debit >= 0", name="findraft_tb_lines_debit_check"),
        CheckConstraint("credit >= 0", name="findraft_tb_lines_credit_check"),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_tb_lines_company_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_tb_lines_org_id", "org_id"),
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
    tb_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findraft_tb_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    nominal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    account_name: Mapped[str] = mapped_column(String(500), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
