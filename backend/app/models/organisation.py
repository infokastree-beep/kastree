"""Organisation SQLAlchemy model."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Organisation(Base):
    __tablename__ = "organisations"
    __table_args__ = (
        CheckConstraint(
            "subscription_tier IN ('free', 'starter', 'pro', 'scale')",
            name="organisations_subscription_tier_check",
        ),
        CheckConstraint(
            "subscription_status IN ('active', 'past_due', 'cancelled', 'trialing')",
            name="organisations_subscription_status_check",
        ),
        Index("idx_organisations_clerk_org_id", "clerk_org_id"),
        Index("idx_organisations_stripe_customer", "stripe_customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clerk_org_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Billing fields: write only from the Stripe webhook handler (§4.5) — never via general org PUT/PATCH or admin bulk-update.
    subscription_tier: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'free'")
    )
    subscription_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'active'")
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    functional_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, server_default=text("'GBP'")
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
