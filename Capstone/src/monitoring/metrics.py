"""
monitoring/metrics.py
---------------------
Prometheus metrics + the @track_agent decorator.

The decorator is the single observability seam: it times the call, records
tokens, counts success/error, updates gauges and emits a structlog line —
so agent code stays 100% free of monitoring boilerplate.

Metrics (all prefixed fiaa_) match the design document exactly.
"""
from __future__ import annotations

import functools
import threading
import time
from typing import Callable

from configs.settings import settings
from monitoring.logger import get_logger, write_run_event

log = get_logger("metrics")

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, start_http_server, REGISTRY,
    )
    _PROM = True
except Exception:  # pragma: no cover
    _PROM = False

# In-process mirror of metrics so the Streamlit monitoring tab can render
# charts even if a Prometheus server isn't scraping yet.
SNAPSHOT = {
    "agent_calls": {},        # agent -> {"success": n, "error": n}
    "agent_latency": {},      # agent -> [durations]
    "agent_tokens": {},       # agent -> [tokens]
    "guardrail_hits": {},     # type -> count
    "last_risk_score": 0.0,
    "active_runs": 0,
    "pipeline_latency": [],   # list of durations
    "supervisor_iterations": [],
    "ragas_faithfulness": 0.0,
}
_lock = threading.Lock()


if _PROM:
    AGENT_CALLS = Counter("fiaa_agent_calls_total", "Agent calls", ["agent", "status"])
    AGENT_LATENCY = Histogram("fiaa_agent_latency_seconds", "Agent latency", ["agent"])
    LLM_TOKENS = Histogram("fiaa_llm_tokens_total", "LLM tokens per agent", ["agent"],
                           buckets=(64, 128, 256, 512, 1024, 2048, 4096, 8192))
    GUARDRAIL_HITS = Counter("fiaa_guardrail_hits_total", "Guardrail hits", ["type", "severity"])
    PIPELINE_LATENCY = Histogram("fiaa_pipeline_latency_seconds", "End-to-end pipeline latency")
    LAST_RISK = Gauge("fiaa_last_risk_score", "Most recent risk score")
    ACTIVE_RUNS = Gauge("fiaa_active_runs", "Concurrent pipelines")
    SUPERVISOR_ITERS = Histogram("fiaa_supervisor_iterations", "Routing iterations per run",
                                 buckets=(1, 2, 3, 4, 5, 6, 8, 10))
    RAGAS_FAITHFULNESS = Gauge("fiaa_ragas_faithfulness", "Most recent RAGAS faithfulness score")


_metrics_server_started = False


def start_metrics_server() -> bool:
    """Expose /metrics on settings.metrics_port (idempotent)."""
    global _metrics_server_started
    if not _PROM or _metrics_server_started:
        return _metrics_server_started
    try:
        start_http_server(settings.metrics_port)
        _metrics_server_started = True
        log.info("metrics.server_started", port=settings.metrics_port)
    except OSError:
        # already bound by another process (e.g. the API process) — fine
        _metrics_server_started = True
    return _metrics_server_started


# ---- helpers used by both the decorator and direct callers ---------------
def record_guardrail(gtype: str, severity: str = "warning") -> None:
    with _lock:
        SNAPSHOT["guardrail_hits"][gtype] = SNAPSHOT["guardrail_hits"].get(gtype, 0) + 1
    if _PROM:
        GUARDRAIL_HITS.labels(type=gtype, severity=severity).inc()


def record_risk_score(score: float) -> None:
    with _lock:
        SNAPSHOT["last_risk_score"] = float(score)
    if _PROM:
        LAST_RISK.set(float(score))


def record_ragas(faithfulness: float) -> None:
    """Record the latest RAGAS faithfulness score (feeds the Grafana alert)."""
    with _lock:
        SNAPSHOT["ragas_faithfulness"] = float(faithfulness)
    if _PROM:
        RAGAS_FAITHFULNESS.set(float(faithfulness))


def record_pipeline_latency(seconds: float) -> None:
    with _lock:
        SNAPSHOT["pipeline_latency"].append(seconds)
    if _PROM:
        PIPELINE_LATENCY.observe(seconds)


def record_iterations(n: int) -> None:
    with _lock:
        SNAPSHOT["supervisor_iterations"].append(n)
    if _PROM:
        SUPERVISOR_ITERS.observe(n)


def inc_active_runs(delta: int) -> None:
    with _lock:
        SNAPSHOT["active_runs"] = max(0, SNAPSHOT["active_runs"] + delta)
    if _PROM:
        ACTIVE_RUNS.inc(delta) if delta > 0 else ACTIVE_RUNS.dec(-delta)


def _record_call(agent: str, status: str, duration: float, tokens: int) -> None:
    with _lock:
        bucket = SNAPSHOT["agent_calls"].setdefault(agent, {"success": 0, "error": 0})
        bucket[status] = bucket.get(status, 0) + 1
        SNAPSHOT["agent_latency"].setdefault(agent, []).append(duration)
        if tokens:
            SNAPSHOT["agent_tokens"].setdefault(agent, []).append(tokens)
    if _PROM:
        AGENT_CALLS.labels(agent=agent, status=status).inc()
        AGENT_LATENCY.labels(agent=agent).observe(duration)
        if tokens:
            LLM_TOKENS.labels(agent=agent).observe(tokens)


def track_agent(agent_name: str) -> Callable:
    """Decorator: wrap an agent node fn(state) -> partial_state.

    Reads `_tokens` and `run_id` from the returned/inbound state to attribute
    token cost. Times the call, counts success/error and emits a log line.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state, *args, **kwargs):
            run_id = (state or {}).get("run_id", "unknown")
            start = time.perf_counter()
            status = "success"
            tokens = 0
            try:
                result = fn(state, *args, **kwargs) or {}
                tokens = int(result.get("_last_tokens", 0))
                return result
            except Exception as e:  # noqa
                status = "error"
                duration = time.perf_counter() - start
                _record_call(agent_name, "error", duration, 0)
                write_run_event(run_id, {
                    "event": "agent.failed", "level": "error",
                    "agent": agent_name, "error": str(e),
                    "duration_s": round(duration, 3),
                })
                log.error("agent.failed", agent=agent_name, error=str(e))
                raise
            finally:
                if status == "success":
                    duration = time.perf_counter() - start
                    _record_call(agent_name, "success", duration, tokens)
                    write_run_event(run_id, {
                        "event": "agent.success", "level": "info",
                        "agent": agent_name, "duration_s": round(duration, 3),
                        "tokens": tokens,
                    })
                    log.info("agent.success", agent=agent_name,
                             duration_s=round(duration, 3), tokens=tokens)
        return wrapper
    return decorator


def snapshot() -> dict:
    """Thread-safe copy of the in-process metrics for the dashboard."""
    import copy
    with _lock:
        return copy.deepcopy(SNAPSHOT)
