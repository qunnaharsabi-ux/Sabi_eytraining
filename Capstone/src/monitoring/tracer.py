"""
monitoring/tracer.py
--------------------
OpenTelemetry span helper. LangSmith tracing is configured purely through
env vars (see settings.get_settings) and picked up automatically by
LangGraph/LangChain. This module adds optional OTel spans around agent
nodes; if OTel isn't installed it degrades to a no-op context manager so
the pipeline never depends on it (matches the "LangSmith down" stress test).
"""
from __future__ import annotations

from contextlib import contextmanager

from configs.settings import settings

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    _OTEL = True
except Exception:  # pragma: no cover
    _OTEL = False

_provider = None
_tracer = None


def init_tracer() -> None:
    global _provider, _tracer
    if not _OTEL or _tracer is not None:
        return
    _provider = TracerProvider(resource=Resource.create({"service.name": "fiaa"}))
    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("fiaa")


@contextmanager
def span(name: str, **attrs):
    if not _OTEL:
        yield None
        return
    if _tracer is None:
        init_tracer()
    with _tracer.start_as_current_span(name) as s:  # type: ignore
        for k, v in attrs.items():
            try:
                s.set_attribute(k, v)
            except Exception:
                pass
        yield s


def langsmith_status() -> str:
    if settings.has_langsmith:
        return f"enabled · project={settings.langchain_project}"
    return "disabled (set LANGCHAIN_TRACING_V2 + LANGCHAIN_API_KEY)"
