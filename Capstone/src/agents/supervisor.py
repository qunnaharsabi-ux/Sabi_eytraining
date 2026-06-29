"""
agents/supervisor.py
--------------------
The routing brain. An LLM call (not hardcoded rules) decides the next agent,
guarded by three loop-safety mechanisms:
  * iteration cap     -> force WRITE after N iterations
  * done-check        -> never re-call a completed agent
  * approval-check    -> END as soon as the Evaluator approves
"""
from __future__ import annotations

import json

from configs.prompts import SUPERVISOR_PROMPT
from configs.settings import settings
from core.llm import chat_json
from graph.state import ResearchState
from monitoring.logger import write_run_event
from monitoring.metrics import track_agent

VALID = {"SEARCH", "RAG", "READER", "WRITE", "END"}


@track_agent("supervisor")
def supervisor_node(state: ResearchState) -> dict:
    it = state.get("iteration", 0)
    done = set(state.get("done", []))
    run_id = state["run_id"]

    decision, reason = _decide(state, it, done)

    write_run_event(run_id, {"event": "supervisor.decision", "level": "info",
                             "next": decision, "reason": reason, "iteration": it})
    timeline = state.get("timeline", []) + [
        {"agent": "supervisor", "detail": f"-> {decision}: {reason}", "iteration": it}]

    return {
        "next": decision,
        "supervisor_reason": reason,
        "iteration": it + 1,
        "timeline": timeline,
        "_last_tokens": state.get("_last_tokens", 0),
    }


def _decide(state: ResearchState, it: int, done: set) -> tuple[str, str]:
    # 1. approval-check
    ev = state.get("evaluation") or {}
    if ev:
        if ev.get("approved"):
            return "END", "Evaluator approved the report"
        return "WRITE", "Evaluator rejected — revise with feedback"

    # 2. iteration cap
    if it >= settings.iteration_cap:
        return "WRITE", "Iteration cap reached — force report"

    # 3. deterministic policy with an LLM advisory layer
    if "search" not in done:
        choice = "SEARCH"
    elif "rag" not in done:
        choice = "RAG"
    elif state.get("document_text") and "reader" not in done:
        choice = "READER"
    else:
        choice = "WRITE"

    # Let the LLM confirm / explain (kept advisory so routing is always safe).
    if not settings.demo_mode:
        try:
            data, res = chat_json(
                SUPERVISOR_PROMPT,
                json.dumps({"alert": state.get("alert"), "done": sorted(done),
                            "iteration": it}),
                model=settings.model_supervisor, max_tokens=120,
            )
            llm_next = str(data.get("next", "")).upper()
            if llm_next in VALID and llm_next != "END":
                # never re-call a done agent
                if llm_next.lower() not in done:
                    choice = llm_next
            return choice, data.get("reason", "policy routing")
        except Exception:
            pass
    return choice, "policy routing"
