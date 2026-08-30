"""FastAPI application factory."""

from fastapi import FastAPI

from app.routers import (
    auth,
    clients,
    export,
    organisations,
    risk,
    trial_balances,
    variance,
    webhooks,
)

app = FastAPI(title="FinDraft API", version="0.1.0")

app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(organisations.router)
app.include_router(trial_balances.router)
app.include_router(variance.router)
app.include_router(risk.router)
app.include_router(export.trial_balances_router)
app.include_router(export.exports_router)
app.include_router(webhooks.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
