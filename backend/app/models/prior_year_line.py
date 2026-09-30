"""Validated prior-year canonical-line balance for one year end."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PriorYearLine(Base):
    __tablename__ = "findraft_prior_year_lines"
    __table_args__ = (
        UniqueConstraint(
            "year_end_id",
            "canonical_line",
            name="findraft_prior_year_lines_line_key",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_prior_year_lines_company_fk",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["year_end_id", "org_id", "company_id"],
            [
                "findraft_year_ends.id",
                "findraft_year_ends.org_id",
                "findraft_year_ends.company_id",
            ],
            name="findraft_prior_year_lines_year_end_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_prior_year_lines_org_id", "org_id"),
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
    canonical_line: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
