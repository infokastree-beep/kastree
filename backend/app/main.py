"""FastAPI application factory."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging
from app.sentry_setup import init_sentry
from app.routers import (
    admin,
    archived_records,
    auth,
    billing,
    clients,
    commentary,
    companies,
    contact,
    copilot,
    export,
    notifications,
    organisations,
    risk,
    solutions,
    trial_balances,
    users,
    variance,
    waitlist,
    webhooks,
)

# Initialise before the FastAPI app so integrations wrap the ASGI stack.
init_sentry()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="FinDraft API", version="0.1.0", lifespan=lifespan)

_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(users.router)
app.include_router(clients.router)
app.include_router(companies.router)
app.include_router(organisations.router)
app.include_router(billing.router)
app.include_router(solutions.router)
app.include_router(trial_balances.router)
app.include_router(variance.router)
app.include_router(waitlist.router)
app.include_router(contact.router)
app.include_router(risk.router)
app.include_router(export.trial_balances_router)
app.include_router(export.exports_router)
app.include_router(webhooks.router)
app.include_router(commentary.router)
app.include_router(copilot.router)
app.include_router(notifications.router)
app.include_router(archived_records.clients_router)
app.include_router(archived_records.org_router)
app.include_router(archived_records.records_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe. Git deploy source: infokastree-beep/kastree (auto-deploy check)."""
    return {"status": "ok"}


@app.get("/sentry-debug")
async def sentry_debug(
    token: str | None = Query(default=None),
) -> None:
    """Deliberate unhandled error for verifying Sentry capture.

    Disabled unless ``SENTRY_DEBUG_TOKEN`` is set and the ``token`` query
    parameter matches. Returns 404 otherwise so the route is not a public
    DoS/noise vector.
    """
    expected = (settings.sentry_debug_token or "").strip()
    if not expected or token != expected:
        raise HTTPException(status_code=404, detail="Not Found")
    raise RuntimeError("Sentry deliberate test error — kastree backend verify")
