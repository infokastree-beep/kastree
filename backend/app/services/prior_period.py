"""Prior-period trial balance resolution shared by variance and upload preview.

Matches Product Spec §6.2 / variance._resolve_prior_tb auto branch:
same company, period_end strictly before the candidate period, most recent first.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.trial_balance import TrialBalance


async def find_prior_trial_balance(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    before_period_end: date,
) -> TrialBalance | None:
    """Return the most recent TB for company with period_end < before_period_end."""
    result = await session.execute(
        select(TrialBalance)
        .where(
            TrialBalance.company_id == company_id,
            TrialBalance.period_end < before_period_end,
        )
        .order_by(TrialBalance.period_end.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
