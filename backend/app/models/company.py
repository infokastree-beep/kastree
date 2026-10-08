"""Company SQLAlchemy model — entity under a client group."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="companies_org_id_id_key"),
        Index("idx_companies_org_id", "org_id"),
        Index("idx_companies_client_id", "client_id"),
        Index("idx_companies_client_deleted", "client_id", "is_deleted"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Tenant key for Product 2 composite FKs. Same organisation id RLS already
    # uses via app.current_org_id. The insert trigger copies it from the client
    # when omitted and rejects a mismatch.
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Statutory entity record captured once (v7.6 §4.7). Nullable until entered.
    registered_office: Mapped[str | None] = mapped_column(String, nullable=True)
    directors: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, nullable=True
    )
    secretary: Mapped[str | None] = mapped_column(String, nullable=True)
    financial_year_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    average_employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    functional_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'GBP'")
    )
    company_number: Mapped[str | None] = mapped_column(String, nullable=True)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    # Letterhead. industry stays the Product 1 field and is not reused here.
    business_address: Mapped[str | None] = mapped_column(String, nullable=True)
    incorporated_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    principal_activity: Mapped[str | None] = mapped_column(String, nullable=True)
    # Letterhead lists. Migration f2a3b4c5d6 added the columns.
    advisers: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, nullable=True
    )
    share_classes: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, nullable=True
    )
    company_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'trading'")
    )
    materiality_threshold_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("10.00")
    )
    materiality_threshold_abs: Mapped[Decimal] = mapped_column(
        Numeric(19, 2), nullable=False, server_default=text("1000.00")
    )
    materiality_suggestion_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
