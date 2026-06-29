"""
agents/rag_agent.py
-------------------
ChromaDB cosine retrieval of the top-5 precedent cases / playbooks / RBI rules,
then an LLM summary of which precedent and procedure apply.
"""
from __future__ import annotations

import json

from configs.prompts import RAG_PROMPT
from configs.settings import settings
from core.llm import chat
from graph.state import ResearchState
from monitoring.metrics import track_agent
from monitoring.logger import write_run_event
from rag.ingestor import retrieve


@track_agent("rag_agent")
def rag_node(state: ResearchState) -> dict:
    inc = state.get("incident", {}) or state.get("alert", {})
    query = (f"{inc.get('category','')} {inc.get('destination','')} "
             f"{' '.join(inc.get('signals',[]))} amount {inc.get('amount','')}")
    chunks = retrieve(query, k=settings.rag_top_k)

    for c in chunks:
        write_run_event(state["run_id"], {
            "event": "rag_agent.chunk", "level": "info",
            "case_id": c["meta"].get("case_id", c["meta"].get("source")),
            "similarity": c.get("similarity"), "source": c["meta"].get("source")})

    ctx = "\n".join(f"[{c.get('similarity')}] ({c['meta'].get('source')}) {c['text']}"
                    for c in chunks) or "(knowledge base empty — degrade to LOW confidence)"
    res = chat(RAG_PROMPT, f"Alert: {json.dumps(inc)}\n\nRetrieved chunks:\n{ctx}",
               model=settings.model_small, max_tokens=500)

    done = state.get("done", []) + ["rag"]
    timeline = state.get("timeline", []) + [
        {"agent": "rag_agent", "detail": f"retrieved {len(chunks)} precedent chunks"}]
    return {"rag_chunks": chunks, "rag_summary": res.text, "done": done,
            "timeline": timeline, "_last_tokens": res.total_tokens}
