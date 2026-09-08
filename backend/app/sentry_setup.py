"""Sentry SDK bootstrap — optional; no-op when SENTRY_DSN is unset."""

from __future__ import annotations

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.config import settings


def init_sentry() -> bool:
    """Initialise Sentry if ``SENTRY_DSN`` is configured.

    Returns True when the SDK was initialised. Errors are always sampled when
    enabled; performance traces use a low rate to stay within free-tier limits.
    ``send_default_pii`` stays False (Privacy by Design / GDPR).
    """
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.app_env,
        release=f"kastree-backend@{settings.app_version}",
        send_default_pii=False,
        traces_sample_rate=0.05 if settings.app_env == "production" else 0.0,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
    return True
