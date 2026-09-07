"""Organisation subscription tier → client-count limits.

Pricing page mapping (marketing → DB CHECK values):
  Free → free (3)
  Starter → starter (10)
  Growth → pro (30)
  Practice → scale (75)

Enforcement is server-side on POST /clients only. Soft-deleted clients do not
count. Billing column writes remain sole to the Stripe webhook path.
"""

from __future__ import annotations

from typing import Final

# DB CHECK: organisations.subscription_tier IN ('free','starter','pro','scale')
CLIENT_LIMITS: Final[dict[str, int]] = {
    "free": 3,
    "starter": 10,
    "pro": 30,
    "scale": 75,
}

DEFAULT_TIER = "free"

PAID_TIERS: Final[frozenset[str]] = frozenset({"starter", "pro", "scale"})

# Public upgrade message — keep stable; frontend links to /pricing.
CLIENT_LIMIT_MESSAGE = (
    "You've reached your plan's client limit ({limit}). "
    "Upgrade to add more clients."
)


def client_limit_for_tier(tier: str | None) -> int:
    """Return the active-client cap for a subscription_tier value."""
    if tier is None:
        return CLIENT_LIMITS[DEFAULT_TIER]
    return CLIENT_LIMITS.get(tier, CLIENT_LIMITS[DEFAULT_TIER])


def format_client_limit_message(limit: int) -> str:
    return CLIENT_LIMIT_MESSAGE.format(limit=limit)
