"""FastAPI app factory. Implementation pending."""

from fastapi import FastAPI

app = FastAPI(title="FinDraft API", version="0.1.0")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
