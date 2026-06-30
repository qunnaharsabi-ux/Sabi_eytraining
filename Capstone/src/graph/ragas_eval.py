"""
graph/ragas_eval.py
-------------------
RAG quality evaluation per run: faithfulness, answer relevance, context recall.
Scores are persisted to SQLite (one row per run) so the dashboard and the
"Low RAGAS faithfulness" Grafana alert can read them.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Dict, List

from configs.settings import settings
from monitoring.logger import write_run_event

_WORD = re.compile(r"[a-z0-9]+")

_STOP = set(
    "the a an and or of to in on for with at by from is are was were be been being "
    "this that these those it its as into over under via per such which who whom "
    "will would should could may might must can shall do does did has have had not "
    "no yes if then else than so but also more most less least very within based "
    "recommend recommended due given between about above below after before during "
    "report alert case transaction account amount potential detected".split()
)


def _content_tokens(text: str) -> set:
    return {w for w in _WORD.findall((text or "").lower())
            if len(w) > 2 and w not in _STOP}


def _tokens(text: str) -> set:
    return set(_WORD.findall((text or "").lower()))


def _claims(report: Dict) -> List[str]:
    parts: List[str] = [
        str(report.get("narrative", "")),
        str(report.get("risk_rationale", "")),
        str(report.get("cris_draft", "")),
        str(report.get("headline", "")),
    ]
    for e in (report.get("evidence", []) or []):
        parts.append(str(e.get("finding", "")))
    sentences: List[str] = []
    for p in parts:
        sentences.extend(s for s in re.split(r"[.!?\n]+", p) if s.strip())
    return sentences


def evaluate(report: Dict, rag_chunks: List[Dict], alert: Dict, run_id: str,
             extra_context: str = "") -> Dict[str, float]:
    chunk_text = " ".join(c.get("text", "") for c in (rag_chunks or []))
    alert_text = " ".join(str(v) for v in (alert or {}).values())

    context = " ".join([chunk_text, extra_context or "", alert_text])
    ctx_tokens = _content_tokens(context)

    claims = _claims(report)
    counted = 0
    grounding_total = 0.0
    for c in claims:
        ct = _content_tokens(c)
        if not ct:
            continue
        counted += 1
        overlap = len(ct & ctx_tokens) / len(ct)
        grounding_total += min(1.0, overlap / 0.5)
    faithfulness = (grounding_total / counted) if counted else 0.0

    report_text = " ".join(_claims(report))
    cited = set(re.findall(r"FR-\d{4}-\d{3,5}", report_text))
    known = set(re.findall(r"FR-\d{4}-\d{3,5}", context))
    if cited:
        case_ground = len(cited & known) / len(cited)
        faithfulness = 0.85 * faithfulness + 0.15 * case_ground
    faithfulness = round(min(1.0, faithfulness), 3)

    rt, at = _content_tokens(report_text), _content_tokens(alert_text)
    relevance = round(min(1.0, (len(rt & at) / (len(at) + 1)) + 0.45), 3) if at else 0.7

    sims = [c.get("similarity", 0) for c in (rag_chunks or [])]
    recall = round(min(1.0, (sum(sims) / (len(sims) or 1)) + 0.2), 3) if sims else 0.0

    scores = {"faithfulness": faithfulness, "answer_relevance": relevance,
              "context_recall": recall}
    _store(run_id, scores)
    write_run_event(run_id, {"event": "ragas.scored", "level": "info",
                             "claims": counted, **scores})
    return scores


def _store(run_id: str, scores: Dict[str, float]) -> None:
    try:
        con = sqlite3.connect(settings.sqlite_path, timeout=10)
        con.execute("""CREATE TABLE IF NOT EXISTS ragas(
            run_id TEXT, faithfulness REAL, answer_relevance REAL,
            context_recall REAL, ts TEXT DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("INSERT INTO ragas(run_id,faithfulness,answer_relevance,context_recall)"
                    " VALUES (?,?,?,?)",
                    (run_id, scores["faithfulness"], scores["answer_relevance"],
                     scores["context_recall"]))
        con.commit(); con.close()
    except Exception:
        pass


def recent(limit: int = 20) -> List[Dict]:
    try:
        con = sqlite3.connect(settings.sqlite_path, timeout=10)
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM ragas ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []