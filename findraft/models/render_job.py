"""DOCX render jobs. The request handler inserts a pending row.

A worker claims the row. This is not an auditor attachment and not a Celery task.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RenderJob(Base):
    __tablename__ = "findraft_render_jobs"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "idempotency_key",
            name="findraft_render_jobs_idempotency_key",
        ),
        UniqueConstraint(
            "id",
            "org_id",
            "company_id",
            name="findraft_render_jobs_id_org_company_key",
        ),
        CheckConstraint(
            "format = 'docx'",
            name="findraft_render_jobs_format_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed')",
            name="findraft_render_jobs_status_check",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_render_jobs_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tb_version_id", "org_id", "company_id"],
            [
                "findraft_tb_versions.id",
                "findraft_tb_versions.org_id",
                "findraft_tb_versions.company_id",
            ],
            name="findraft_render_jobs_version_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_render_jobs_org_id", "org_id"),
        Index("idx_findraft_render_jobs_tb_version_id", "tb_version_id"),
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
    tb_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    format: Mapped[str] = mapped_column(
        String(8), nullable=False, default="docx", server_default="docx"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    watermark: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
