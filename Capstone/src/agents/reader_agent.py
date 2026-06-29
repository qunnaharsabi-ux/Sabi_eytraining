"""
agents/reader_agent.py
----------------------
Extracts decision-relevant facts from an uploaded KYC PDF / statement.
Only runs when a document was uploaded. PyMuPDF does the extraction;
the small model summarises.
"""
from __future__ import annotations

from configs.prompts import READER_PROMPT
from configs.settings import settings
from core.llm import chat
from graph.state import ResearchState
from monitoring.metrics import track_agent
from monitoring.logger import write_run_event


def extract_pdf_text(path_or_bytes) -> str:
    try:
        import fitz  # PyMuPDF
        if isinstance(path_or_bytes, (bytes, bytearray)):
            doc = fitz.open(stream=path_or_bytes, filetype="pdf")
        else:
            doc = fitz.open(path_or_bytes)
        return "\n".join(page.get_text() for page in doc)[:8000]
    except Exception:
        return ""


@track_agent("reader_agent")
def reader_node(state: ResearchState) -> dict:
    text = state.get("document_text") or ""
    if not text.strip():
        done = state.get("done", []) + ["reader"]
        return {"reader_brief": "No document uploaded.", "done": done,
                "timeline": state.get("timeline", []) + [
                    {"agent": "reader_agent", "detail": "skipped (no document)"}],
                "_last_tokens": 0}

    res = chat(READER_PROMPT, text[:6000], model=settings.model_small, max_tokens=400)
    write_run_event(state["run_id"], {"event": "reader.done", "level": "info",
                                      "chars": len(text)})
    done = state.get("done", []) + ["reader"]
    timeline = state.get("timeline", []) + [
        {"agent": "reader_agent", "detail": "KYC/statement brief extracted"}]
    return {"reader_brief": res.text, "done": done, "timeline": timeline,
            "_last_tokens": res.total_tokens}
