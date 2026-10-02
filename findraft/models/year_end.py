"""Pinned reporting period for one company."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class YearEnd(Base):
    __tablename__ = "findraft_year_ends"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "company_id",
            "period_end",
            name="findraft_year_ends_period_key",
        ),
        UniqueConstraint(
            "id",
            "org_id",
            "company_id",
            "pack_id",
            "pack_version",
            name="findraft_year_ends_pin_key",
        ),
        UniqueConstraint(
            "id",
            "org_id",
            "company_id",
            name="findraft_year_ends_id_org_company_key",
        ),
        ForeignKeyConstraint(
            ["org_id", "company_id"],
            ["companies.org_id", "companies.id"],
            name="findraft_year_ends_company_fk",
            ondelete="CASCADE",
        ),
        Index("idx_findraft_year_ends_org_id", "org_id"),
        Index("idx_findraft_year_ends_company_id", "company_id"),
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
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    prior_year_validated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    first_financial_period: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    size_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    size_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_current_met: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_preceding_met: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(16), nullable=False)
    adopted_trial_balance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trial_balances.id", ondelete="SET NULL"),
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
