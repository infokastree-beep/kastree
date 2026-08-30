"""FastAPI application factory."""

from fastapi import FastAPI

from app.routers import auth, trial_balances

app = FastAPI(title="FinDraft API", version="0.1.0")

app.include_router(auth.router)
app.include_router(trial_balances.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
