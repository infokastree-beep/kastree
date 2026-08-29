"""Variance analysis SQLAlchemy model."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VarianceAnalysis(Base):
    __tablename__ = "variance_analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'complete', 'failed')",
            name="variance_analyses_status_check",
        ),
        Index("idx_variance_analyses_tb_id", "tb_id"),
        Index("idx_variance_analyses_prior_tb", "prior_tb_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trial_balances.id", ondelete="CASCADE"),
        nullable=False,
    )
    prior_tb_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trial_balances.id", ondelete="SET NULL"),
        nullable=True,
    )
    items: Mapped[dict] = mapped_column(JSONB, nullable=False)
    commentary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'pending'")
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
