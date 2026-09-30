"""Immutable Product 2 fixed-asset register version and its classes."""

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


class FixedAssetVersion(Base):
    __tablename__ = "findraft_fa_versions"
    __table_args__ = (
        UniqueConstraint(
            "year_end_id",
            "version_number",
            name="findraft_fa_versions_number_key",
        ),
        UniqueConstraint(
            "org_id",
            "idempotency_key",
            name="findraft_fa_versions_idempotency_key",
        ),
        CheckConstraint(
            "version_number >= 1", name="findraft_fa_versions_number_check"
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="findraft_fa_versions_status_check",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_fa_versions_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["year_end_id", "org_id", "company_id"],
            [
                "findraft_year_ends.id",
                "findraft_year_ends.org_id",
                "findraft_year_ends.company_id",
            ],
            name="findraft_fa_versions_year_end_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_document_id", "org_id", "company_id"],
            [
                "findraft_source_documents.id",
                "findraft_source_documents.org_id",
                "findraft_source_documents.company_id",
            ],
            name="findraft_fa_versions_source_fk",
        ),
        Index("idx_findraft_fa_versions_org_id", "org_id"),
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


class FixedAssetLine(Base):
    __tablename__ = "findraft_fa_lines"
    __table_args__ = (
        UniqueConstraint(
            "fa_version_id", "line_no", name="findraft_fa_lines_number_key"
        ),
        UniqueConstraint(
            "fa_version_id", "asset_class", name="findraft_fa_lines_class_key"
        ),
        CheckConstraint("line_no >= 1", name="findraft_fa_lines_line_check"),
        CheckConstraint(
            "opening_cost >= 0", name="findraft_fa_lines_opening_cost_check"
        ),
        CheckConstraint("additions >= 0", name="findraft_fa_lines_additions_check"),
        CheckConstraint("disposals >= 0", name="findraft_fa_lines_disposals_check"),
        CheckConstraint(
            "disposals_dep >= 0", name="findraft_fa_lines_disposals_dep_check"
        ),
        CheckConstraint("opening_dep >= 0", name="findraft_fa_lines_opening_dep_check"),
        CheckConstraint("charge >= 0", name="findraft_fa_lines_charge_check"),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_fa_lines_company_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_fa_lines_org_id", "org_id"),
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
    fa_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findraft_fa_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(200), nullable=False)
    opening_cost: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    additions: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    disposals: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    disposals_dep: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    opening_dep: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    charge: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
