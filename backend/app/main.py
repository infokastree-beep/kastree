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
    audit_logs,
    auth,
    beta,
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
    source_documents,
    trial_balances,
    users,
    variance,
    waitlist,
    webhooks,
    year_ends,
)

# Initialise before the FastAPI app so integrations wrap the ASGI stack.
init_sentry()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="FinDraft API", version="0.1.0", lifespan=lifespan)

_origins = [
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
]
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
app.include_router(trial_balances.router)
app.include_router(source_documents.router)
app.include_router(year_ends.router)
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
app.include_router(audit_logs.router)
app.include_router(beta.router)
app.include_router(archived_records.clients_router)
app.include_router(archived_records.org_router)
app.include_router(archived_records.records_router)


@app.get("/health")
async def health_check() -> dict[str, object]:
    """Liveness probe. Includes git_sha and the database revision.

    A missing or different Alembic revision is reported and does not change
    the status. The process still starts, and this route still returns 200.

    Git deploy source: infokastree-beep/kastree (auto-deploy check).
    """
    from app.services.schema_revision import SchemaRevision, current_schema_revision

    try:
        revision = await current_schema_revision()
    except Exception:
        revision = SchemaRevision(
            database_revision=None,
            code_revision=None,
            revision_matches=False,
        )
    return {
        "status": "ok",
        "git_sha": settings.resolved_git_sha(),
        "database_revision": revision.database_revision,
        "code_revision": revision.code_revision,
        "revision_matches": revision.revision_matches,
    }


@app.get("/version")
async def version() -> dict[str, str]:
    """Deployed backend revision (mirrors the frontend's kastree-git-sha meta tag)."""
    return {
        "version": settings.app_version,
        "git_sha": settings.resolved_git_sha(),
    }


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
