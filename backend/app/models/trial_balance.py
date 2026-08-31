"""Trial balance SQLAlchemy model."""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TrialBalance(Base):
    __tablename__ = "trial_balances"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_end", name="trial_balances_company_id_period_end_key"
        ),
        CheckConstraint(
            "file_type IN ('xlsx', 'csv')",
            name="trial_balances_file_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'parsing', 'mapping', 'validating', "
            "'generating', 'analysing', 'complete', 'failed')",
            name="trial_balances_status_check",
        ),
        Index("idx_trial_balances_company_id", "company_id"),
        Index("idx_trial_balances_company_period", "company_id", "period_end"),
        Index("idx_trial_balances_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    file_url: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parsed_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
    )
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    validation_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
