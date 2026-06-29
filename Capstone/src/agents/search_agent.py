"""
agents/search_agent.py
----------------------
Live web intelligence via Tavily (research-optimised, pre-extracted content).
Synthesises results with the small 8B model to save 70B quota. Degrades to a
demo synthesis when no Tavily key is configured.
"""
from __future__ import annotations

import json

from configs.prompts import SEARCH_PROMPT
from configs.settings import settings
from core.llm import chat
from graph.state import ResearchState
from monitoring.metrics import track_agent
from monitoring.logger import write_run_event

try:
    from tavily import TavilyClient
    _TAVILY = True
except Exception:
    _TAVILY = False


def _web_search(query: str) -> str:
    if not (settings.has_tavily and _TAVILY):
        return ""
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        res = client.search(query=query, max_results=5, search_depth="advanced")
        lines = []
        for r in res.get("results", []):
            lines.append(f"[Source: {r.get('title','web')}] {r.get('content','')[:400]}")
        return "\n".join(lines)
    except Exception:
        return ""


@track_agent("search_agent")
def search_node(state: ResearchState) -> dict:
    inc = state.get("incident", {}) or state.get("alert", {})
    query = (f"bank fraud {inc.get('category','')} {inc.get('destination','')} "
             f"RBI SWIFT recall regulatory deadline {' '.join(inc.get('signals',[]))}")
    raw = _web_search(query)

    user = (f"Alert: {json.dumps(inc)}\n\nWeb results:\n{raw or '(no live results — use general fraud knowledge)'}")
    res = chat(SEARCH_PROMPT, user, model=settings.model_small, max_tokens=500)

    write_run_event(state["run_id"], {"event": "search.done", "level": "info",
                                      "live": bool(raw), "query": query[:120]})
    done = state.get("done", []) + ["search"]
    timeline = state.get("timeline", []) + [
        {"agent": "search_agent", "detail": ("live web intelligence gathered"
                                             if raw else "offline intelligence synthesis")}]
    return {"search_findings": res.text, "done": done, "timeline": timeline,
            "_last_tokens": res.total_tokens}
