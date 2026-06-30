"""
graph/workflow.py
-----------------
Wires the agents into a LangGraph StateGraph and exposes run_pipeline().
"""
from __future__ import annotations

import time
import uuid
from typing import Callable, Dict, List, Optional

from configs.settings import settings
from graph.state import ResearchState, new_state
from graph import ragas_eval

from agents.supervisor import supervisor_node
from agents.incident_agent import incident_node
from agents.search_agent import search_node
from agents.rag_agent import rag_node
from agents.reader_agent import reader_node
from agents.report_agent import report_node
from agents.evaluator_agent import evaluator_node

from guardrails.input_guard import check_input
from guardrails.output_guard import check_output
from monitoring.logger import bind_run, clear_run, write_run_event, get_logger
from monitoring.metrics import (
    inc_active_runs, record_pipeline_latency, record_iterations, start_metrics_server,
    record_ragas,
)
from monitoring.tracer import span

log = get_logger("workflow")

try:
    from langgraph.graph import StateGraph, END
    _LANGGRAPH = True
except Exception:  # pragma: no cover
    _LANGGRAPH = False


def build_graph():
    if not _LANGGRAPH:
        return None
    g = StateGraph(ResearchState)
    g.add_node("incident", incident_node)
    g.add_node("supervisor", supervisor_node)
    g.add_node("search", search_node)
    g.add_node("rag", rag_node)
    g.add_node("reader", reader_node)
    g.add_node("report", report_node)
    g.add_node("evaluator", evaluator_node)

    g.set_entry_point("incident")
    g.add_edge("incident", "supervisor")

    def route(state: ResearchState):
        nxt = state.get("next", "WRITE")
        return {"SEARCH": "search", "RAG": "rag", "READER": "reader",
                "WRITE": "report", "END": END}.get(nxt, "report")

    g.add_conditional_edges("supervisor", route,
                            {"search": "search", "rag": "rag", "reader": "reader",
                             "report": "report", END: END})
    for n in ("search", "rag", "reader"):
        g.add_edge(n, "supervisor")
    g.add_edge("report", "evaluator")
    g.add_edge("evaluator", "supervisor")
    return g.compile()


_compiled = build_graph()


def _manual_run(state: ResearchState, on_event: Optional[Callable] = None) -> ResearchState:
    NODES = {"search": search_node, "rag": rag_node, "reader": reader_node,
             "report": report_node, "evaluator": evaluator_node}

    def emit(node):
        if on_event:
            on_event(node, state)

    state.update(incident_node(state)); emit("incident")
    guard = 0
    while guard < 20:
        guard += 1
        state.update(supervisor_node(state)); emit("supervisor")
        nxt = state.get("next", "WRITE")
        if nxt == "END":
            break
        node_name = {"SEARCH": "search", "RAG": "rag", "READER": "reader",
                     "WRITE": "report"}.get(nxt, "report")
        state.update(NODES[node_name](state)); emit(node_name)
        if node_name == "report":
            state.update(evaluator_node(state)); emit("evaluator")
    return state


def run_pipeline(alert: Dict, document_text: Optional[str] = None,
                 on_event: Optional[Callable] = None) -> Dict:
    """Run the full FIAA pipeline for one alert. Returns a result dict."""
    start_metrics_server()
    run_id = uuid.uuid4().hex[:8]
    bind_run(run_id, alert_id=alert.get("alert_id"), env=settings.env)
    inc_active_runs(1)
    t0 = time.perf_counter()

    write_run_event(run_id, {"event": "pipeline.start", "level": "info",
                             "alert_id": alert.get("alert_id"),
                             "trigger_len": len(str(alert)), "env": settings.env})

    guard = check_input(alert, run_id)
    if not guard.ok:
        inc_active_runs(-1)
        clear_run()
        return {"run_id": run_id, "blocked": True, "reason": guard.reason,
                "flags": guard.flags}

    state = new_state(run_id, guard.cleaned, document_text)
    state["guardrail_notes"] = (
        [f"PII redacted: {', '.join(guard.redacted_fields)}"] if guard.redacted_fields else [])

    try:
        with span("fiaa.pipeline", run_id=run_id):
            if _compiled is not None and on_event is None:
                state = _compiled.invoke(state, config={"recursion_limit": 50})
            else:
                state = _manual_run(state, on_event)
    except Exception as e:
        log.error("pipeline.error", error=str(e))
        inc_active_runs(-1)
        clear_run()
        return {"run_id": run_id, "blocked": False, "error": str(e)}

    report = state.get("report", {})

    rag_ctx = " ".join(c.get("text", "") for c in state.get("rag_chunks", []))
    og = check_output(report, rag_ctx, run_id)
    notes = state.get("guardrail_notes", []) + og.notes

    # ---- RAGAS -----------------------------------------------------------
    # Score faithfulness against EVERYTHING the report could rely on — not just
    # the RAG chunks — so search/KYC/incident-grounded claims are credited.
    extra_context = " ".join([
        state.get("search_findings", "") or "",
        state.get("reader_brief", "") or "",
        state.get("rag_summary", "") or "",
        " ".join(str(v) for v in (state.get("incident", {}) or {}).values()),
    ])
    ragas = ragas_eval.evaluate(report, state.get("rag_chunks", []),
                                state.get("alert", {}), run_id,
                                extra_context=extra_context)
    try:
        record_ragas(float(ragas.get("faithfulness", 0.0)))
    except Exception:
        pass

    score = float(report.get("risk_score", 5.0))
    approved = state.get("evaluation", {}).get("approved", True)
    if not approved:
        decision = "reinvestigate"
    elif score >= settings.high_risk_threshold or "hallucination" in og.flags:
        decision = "human_review"
    else:
        decision = "auto_close"

    iterations = state.get("iteration", 0)
    record_iterations(iterations)
    duration = time.perf_counter() - t0
    record_pipeline_latency(duration)

    write_run_event(run_id, {"event": "pipeline.complete", "level": "info",
                             "iterations": iterations,
                             "total_tokens": state.get("total_tokens", 0),
                             "risk_score": score, "duration_s": round(duration, 2),
                             "approved": approved, "decision": decision})
    inc_active_runs(-1)
    clear_run()

    return {
        "run_id": run_id,
        "blocked": False,
        "alert": state.get("alert", {}),
        "incident": state.get("incident", {}),
        "search_findings": state.get("search_findings", ""),
        "rag_summary": state.get("rag_summary", ""),
        "rag_chunks": state.get("rag_chunks", []),
        "reader_brief": state.get("reader_brief", ""),
        "report": report,
        "evaluation": state.get("evaluation", {}),
        "ragas": ragas,
        "decision": decision,
        "guardrail_notes": notes,
        "output_flags": og.flags,
        "timeline": state.get("timeline", []),
        "iterations": iterations,
        "total_tokens": state.get("total_tokens", 0),
        "duration_s": round(duration, 2),
        "demo_mode": settings.demo_mode,
    }