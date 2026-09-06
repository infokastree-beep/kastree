"""In-memory rate limiting for public endpoints and Copilot.

Process-local only (no Redis). Sufficient for a single-instance MVP; multi-instance
deploys get per-pod limits, which is still better than no limit.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status

_lock = threading.Lock()
_hits: dict[str, list[datetime]] = defaultdict(list)


def client_ip(request: Request) -> str:
    """Best-effort client IP (honours X-Forwarded-For when behind a proxy)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    key_prefix: str,
    max_requests: int,
    window: timedelta,
) -> None:
    """Raise HTTP 429 when ``key_prefix:client_ip`` exceeds ``max_requests`` in ``window``."""
    enforce_rate_limit_key(
        key=f"{key_prefix}:{client_ip(request)}",
        max_requests=max_requests,
        window=window,
    )


def enforce_rate_limit_key(
    *,
    key: str,
    max_requests: int,
    window: timedelta,
) -> None:
    """Raise HTTP 429 when ``key`` exceeds ``max_requests`` in ``window``."""
    if max_requests <= 0:
        return

    now = datetime.now(timezone.utc)
    cutoff = now - window

    with _lock:
        recent = [ts for ts in _hits[key] if ts > cutoff]
        if len(recent) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )
        recent.append(now)
        _hits[key] = recent


def reset_rate_limits_for_tests() -> None:
    """Clear the in-memory bucket (pytest only)."""
    with _lock:
        _hits.clear()
