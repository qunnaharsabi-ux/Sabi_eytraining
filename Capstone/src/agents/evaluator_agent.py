"""
agents/evaluator_agent.py
-------------------------
The reviewer in a preparer-reviewer model. Quality-gates the report on
evidence grounding, score proportionality, PII safety and RBI deadline
accuracy. Runs RAGAS-style scoring alongside (see graph.workflow).
"""
from __future__ import annotations

import json

from configs.prompts import EVALUATOR_PROMPT
from configs.settings import settings
from core.llm import chat_json
from graph.state import ResearchState
from monitoring.metrics import track_agent
from monitoring.logger import write_run_event


@track_agent("evaluator_agent")
def evaluator_node(state: ResearchState) -> dict:
    report = state.get("report", {})
    context = {
        "incident": state.get("incident", {}),
        "search": state.get("search_findings", ""),
        "rag": state.get("rag_summary", ""),
        "rag_cases": [c["meta"].get("case_id") for c in state.get("rag_chunks", [])],
    }
    payload = json.dumps({"report": report, "context": context}, default=str)
    data, res = chat_json(EVALUATOR_PROMPT, payload,
                          model=settings.model_evaluator, max_tokens=350)

    data.setdefault("approved", True)
    data.setdefault("score", 0.85)
    data.setdefault("flags", [])
    data.setdefault("feedback", "")

    # Hard guard: a report citing zero evidence is never auto-approved.
    if not report.get("evidence"):
        data["approved"] = False
        data["flags"] = list(set(data["flags"] + ["no_evidence"]))
        data["feedback"] = "Add grounded evidence items before approval."

    write_run_event(state["run_id"], {"event": "evaluator.decision", "level": "info",
                                      "approved": data["approved"],
                                      "score": report.get("risk_score"),
                                      "flags": data["flags"]})
    timeline = state.get("timeline", []) + [
        {"agent": "evaluator_agent",
         "detail": f"{'approved' if data['approved'] else 'rejected'} (q={data['score']})"}]
    return {"evaluation": data, "eval_feedback": data.get("feedback", ""),
            "timeline": timeline, "_last_tokens": res.total_tokens}
