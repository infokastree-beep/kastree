"""Pinned reporting period for one company."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # Figures accepted by the size check. NULL until that check is stored.
    size_current_turnover: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 2), nullable=True
    )
    size_current_balance_sheet: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 2), nullable=True
    )
    size_current_employees: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_preceding_turnover: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 2), nullable=True
    )
    size_preceding_balance_sheet: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 2), nullable=True
    )
    size_preceding_employees: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # NULL until an owner or admin records the position. True is claimed.
    # False is not claimed. There is no server default.
    audit_exemption_claimed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    audit_exemption_claimed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    audit_exemption_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # NULL until an owner or admin records the three directors' confirmations.
    # There is no server default. One who and when covers the set.
    audit_exemption_not_excluded: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    audit_exemption_no_member_notice: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    audit_exemption_returns_not_late: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    audit_exemption_conditions_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    audit_exemption_conditions_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_version: Mapped[str] = mapped_column(String(16), nullable=False)
    adopted_trial_balance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trial_balances.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Display settings for the draft workspace. The statement engine does not read this.
    report_setup: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    approval_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    signing_directors: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # Directors' report facts. NULL is not recorded. There is no server default.
    # Companies Act 2014, sections 326, 328 and 329. Section 288 uses the
    # period-change flag for the length notice only.
    accounting_records_location: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    interim_dividend: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 2), nullable=True, default=None
    )
    recommended_dividend: Mapped[Decimal | None] = mapped_column(
        Numeric(19, 2), nullable=True, default=None
    )
    share_interests: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    own_shares_particulars: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    subsequent_events_particulars: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    # Preparer particulars. NULL is not recorded. The note engine does not
    # calculate them. Revision x0y1z2a3b4.
    related_party_particulars: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    directors_remuneration_particulars: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    loan_terms_particulars: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    guarantee_particulars: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    research_development_relevant: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    research_development_detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    political_donations_relevant: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    political_donations_detail: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    accounting_period_change_filed: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    # Practice compilation report. Not the directors' approval of the statements.
    compilation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    compilation_signatory: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Acknowledgement that this year end reports in the company currency.
    # A later change of companies.functional_currency no longer matches.
    currency_confirmed_code: Mapped[str | None] = mapped_column(
        String(3), nullable=True
    )
    currency_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    currency_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Comparative source. NULL until a member confirms one. Revision y1z2a3b4c5.
    comparative_source: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )
    comparative_source_trial_balance_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, default=None
    )
    comparative_source_year_end_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, default=None
    )
    comparative_source_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, default=None
    )
    comparative_source_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
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
