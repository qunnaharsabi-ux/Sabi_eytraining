"""
api/webhook.py
--------------
FastAPI webhook that the bank rule engine (or a curl / Invoke-WebRequest call)
hits. It responds in <100 ms with {"status": "accepted"} and runs the full
multi-agent pipeline as a background task — the caller is never kept waiting.

WHAT CHANGED (the fix for "alerts not reflecting in the dashboard")
===================================================================
The webhook now writes to the shared on-disk store (core.store):

  1. The instant an alert arrives  -> store.enqueue_inbox_alert(...)
     so the Streamlit dashboard's "Incoming alert queue" shows it immediately.
  2. When the pipeline finishes     -> store.save_run(...)
     so the dashboard's Investigation tab + history pick it up.

Because the dashboard reads the same SQLite file, alerts fired here now appear
there automatically (the dashboard polls every few seconds).

Run:  uvicorn api.webhook:app --host 0.0.0.0 --port 8001
"""
from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from configs.settings import settings
from core import store
from graph.workflow import run_pipeline
from monitoring.metrics import start_metrics_server
from monitoring.logger import get_logger

log = get_logger("api")

# in-process cache (handy for the /api/result/{id} lookups); the durable copy
# lives in the shared store so the dashboard can see it from its own process.
RESULTS: Dict[str, dict] = {}
_RATE: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT, RATE_WINDOW = 60, 60  # 60 requests / minute / client


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # startup
    store.init_db()
    start_metrics_server()
    log.info("api.started", port=settings.api_port, demo_mode=settings.demo_mode)
    yield
    # shutdown (nothing to clean up)


app = FastAPI(
    title="FIAA Webhook",
    version="2.1",
    description="Fraud Intelligence AI Assistant — alert ingestion webhook",
    lifespan=lifespan,
)


class Alert(BaseModel):
    alert_id: str = Field(..., examples=["FR-2025-8821"])
    account: Optional[str] = Field(None, examples=["****4729"])
    amount: float = Field(..., examples=[487000])
    currency: str = "INR"
    destination: Optional[str] = Field(None, examples=["Cayman Islands"])
    signals: List[str] = Field(default_factory=list)
    sla_minutes: int = 120
    channel: Optional[str] = "wire"


def _auth(x_api_key: Optional[str]) -> None:
    if x_api_key != settings.fiaa_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def _rate_limit(client: str) -> None:
    now = time.time()
    _RATE[client] = [t for t in _RATE[client] if now - t < RATE_WINDOW]
    if len(_RATE[client]) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _RATE[client].append(now)


def _run_and_store(alert: dict) -> None:
    """Background task: run the pipeline and persist the result for the UI."""
    try:
        result = run_pipeline(alert)
        RESULTS[result["run_id"]] = result
        RESULTS["__latest__"] = result
        # durable, cross-process copy the dashboard reads:
        store.save_run(result, source="webhook")
        store.set_inbox_status(alert.get("alert_id"), "done")
    except Exception as e:  # never let a background crash go silent
        log.error("webhook.pipeline_failed", error=str(e),
                  alert_id=alert.get("alert_id"))
        store.set_inbox_status(alert.get("alert_id"), "error")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "demo_mode": settings.demo_mode,
            "groq": settings.has_groq, "tavily": settings.has_tavily,
            "langsmith": settings.has_langsmith}


@app.post("/api/analyse")
async def analyse(alert: Alert, request: Request, background: BackgroundTasks,
                  x_api_key: Optional[str] = Header(None)) -> dict:
    _auth(x_api_key)
    _rate_limit(request.client.host if request.client else "unknown")

    payload = alert.model_dump()
    if len(str(payload)) > settings.max_alert_chars:
        raise HTTPException(status_code=400, detail="Alert payload too large")

    # 1) make it visible on the dashboard queue immediately
    store.enqueue_inbox_alert(payload, status="processing")
    # 2) respond at once; investigate in the background
    background.add_task(_run_and_store, payload)
    return {"status": "accepted", "alert_id": alert.alert_id}


@app.get("/api/result/{run_id}")
def get_result(run_id: str) -> dict:
    if run_id in RESULTS:
        return RESULTS[run_id]
    found = store.get_run(run_id)        # fall back to the shared store
    if found:
        return found
    raise HTTPException(status_code=404, detail="run_id not found")


@app.get("/api/latest")
def latest() -> dict:
    if "__latest__" in RESULTS:
        return RESULTS["__latest__"]
    runs = store.latest_runs(1)
    return runs[0] if runs else {"status": "no runs yet"}
