"""One draft of a pinned year end. Pack identity matches the parent pin."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DraftVersion(Base):
    __tablename__ = "findraft_draft_versions"
    __table_args__ = (
        UniqueConstraint(
            "year_end_id",
            "version_number",
            name="findraft_draft_versions_number_key",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_draft_versions_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["year_end_id", "org_id", "company_id", "pack_id", "pack_version"],
            [
                "findraft_year_ends.id",
                "findraft_year_ends.org_id",
                "findraft_year_ends.company_id",
                "findraft_year_ends.pack_id",
                "findraft_year_ends.pack_version",
            ],
            name="findraft_draft_versions_pin_fk",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('draft', 'locked', 'final')",
            name="findraft_draft_versions_status_check",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="findraft_draft_versions_version_check",
        ),
        Index("idx_findraft_draft_versions_org_id", "org_id"),
        Index("idx_findraft_draft_versions_year_end_id", "year_end_id"),
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
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    tb_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("findraft_tb_versions.id"),
        nullable=True,
    )
    row_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    snapshot: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    inputs_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finalised_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
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
