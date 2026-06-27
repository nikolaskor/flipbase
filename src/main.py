"""FastAPI-app: helsesjekk, manuell trigger og enkelt dashboard-endepunkt."""
from __future__ import annotations

from fastapi import FastAPI

from src.scheduler import run_once

app = FastAPI(title="FlipBase")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/run")
async def trigger_run() -> dict:
    """Manuell kjoring av en full scrape/evaluerings-syklus."""
    await run_once()
    return {"status": "completed"}
