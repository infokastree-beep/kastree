"""Financial statement SQLAlchemy model."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (
        CheckConstraint(
            "statement_type IN ('SOPL', 'SOFP', 'SOCIE')",
            name="financial_statements_statement_type_check",
        ),
        Index("idx_financial_statements_tb_id", "tb_id"),
        Index("idx_financial_statements_tb_type", "tb_id", "statement_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tb_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trial_balances.id", ondelete="CASCADE"),
        nullable=False,
    )
    statement_type: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
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
