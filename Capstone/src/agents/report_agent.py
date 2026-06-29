"""
agents/report_agent.py
----------------------
The Report Agent — reserved for the 70B model because report quality is
critical. Synthesises incident + search + RAG + reader context into a
structured fraud incident report (risk score, evidence, CRIS draft, actions).
"""
from __future__ import annotations

import json

from configs.prompts import REPORT_PROMPT
from configs.settings import settings
from core.llm import chat_json
from graph.state import ResearchState
from monitoring.metrics import track_agent, record_risk_score
from monitoring.logger import write_run_event


def _build_context(state: ResearchState) -> str:
    parts = {
        "incident": state.get("incident", {}),
        "web_intelligence": state.get("search_findings", ""),
        "rag_precedent": state.get("rag_summary", ""),
        "rag_cases": [c["meta"].get("case_id") for c in state.get("rag_chunks", [])
                      if c["meta"].get("case_id")],
        "document_brief": state.get("reader_brief", ""),
        "evaluator_feedback": state.get("eval_feedback", ""),
    }
    return json.dumps(parts, indent=2, default=str)


@track_agent("report_agent")
def report_node(state: ResearchState) -> dict:
    ctx = _build_context(state)
    data, res = chat_json(REPORT_PROMPT, ctx, model=settings.model_report, max_tokens=1400)

    # safety defaults
    data.setdefault("risk_score", 5.0)
    try:
        data["risk_score"] = round(float(data["risk_score"]), 1)
    except Exception:
        data["risk_score"] = 5.0
    data.setdefault("evidence", [])
    data.setdefault("recommended_actions", [])
    data.setdefault("confidence", "medium")

    record_risk_score(data["risk_score"])
    write_run_event(state["run_id"], {"event": "agent.success", "level": "info",
                                      "agent": "report_agent",
                                      "risk_score": data["risk_score"],
                                      "tokens": res.total_tokens})
    timeline = state.get("timeline", []) + [
        {"agent": "report_agent", "detail": f"report drafted · risk {data['risk_score']}"}]
    # reset evaluation so the supervisor re-evaluates the revised report
    return {"report": data, "evaluation": {}, "timeline": timeline,
            "total_tokens": state.get("total_tokens", 0) + res.total_tokens,
            "_last_tokens": res.total_tokens}
