"""Confirmed statutory mapping for one immutable trial-balance version.

Insert-only. There is no updated_at: a confirmed row is not edited.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ConfirmedMapping(Base):
    __tablename__ = "findraft_confirmed_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tb_version_id",
            "nominal_code",
            name="findraft_confirmed_mappings_code_key",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_confirmed_mappings_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tb_version_id", "org_id", "company_id"],
            [
                "findraft_tb_versions.id",
                "findraft_tb_versions.org_id",
                "findraft_tb_versions.company_id",
            ],
            name="findraft_confirmed_mappings_version_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_confirmed_mappings_org_id", "org_id"),
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
    nominal_code: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_line: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
