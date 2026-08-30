"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    archived_records,
    auth,
    clients,
    commentary,
    export,
    notifications,
    organisations,
    risk,
    trial_balances,
    variance,
    webhooks,
)

app = FastAPI(title="FinDraft API", version="0.1.0")

_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(organisations.router)
app.include_router(trial_balances.router)
app.include_router(variance.router)
app.include_router(risk.router)
app.include_router(export.trial_balances_router)
app.include_router(export.exports_router)
app.include_router(webhooks.router)
app.include_router(commentary.router)
app.include_router(notifications.router)
app.include_router(archived_records.clients_router)
app.include_router(archived_records.org_router)
app.include_router(archived_records.records_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
