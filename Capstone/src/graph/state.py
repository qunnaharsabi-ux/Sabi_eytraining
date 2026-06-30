"""
graph/state.py
--------------
The typed shared state that flows through the LangGraph StateGraph.
Every agent reads from and writes a partial update to this dict.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class ResearchState(TypedDict, total=False):
    # identity
    run_id: str
    alert: Dict[str, Any]            # cleaned alert payload (post-guardrail)
    document_text: Optional[str]     # text of an uploaded PDF, if any

    # supervisor control
    next: str                        # SEARCH | RAG | READER | WRITE | END
    iteration: int
    done: List[str]                  # agents already completed
    supervisor_reason: str

    # agent outputs
    incident: Dict[str, Any]
    search_findings: str
    rag_chunks: List[Dict[str, Any]]
    rag_summary: str
    reader_brief: str

    # report + evaluation
    report: Dict[str, Any]
    evaluation: Dict[str, Any]
    eval_feedback: str

    # accounting / telemetry
    total_tokens: int
    _last_tokens: int                # set by each node, read by @track_agent

    # final
    decision: str                    # human_review | auto_close | reinvestigate
    guardrail_notes: List[str]
    timeline: List[Dict[str, Any]]   # ordered agent events for the UI


def new_state(run_id: str, alert: Dict[str, Any],
              document_text: Optional[str] = None) -> ResearchState:
    return ResearchState(
        run_id=run_id,
        alert=alert,
        document_text=document_text,
        next="",
        iteration=0,
        done=[],
        supervisor_reason="",
        incident={},
        search_findings="",
        rag_chunks=[],
        rag_summary="",
        reader_brief="",
        report={},
        evaluation={},
        eval_feedback="",
        total_tokens=0,
        _last_tokens=0,
        decision="",
        guardrail_notes=[],
        timeline=[],
    )
