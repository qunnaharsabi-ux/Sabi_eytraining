"""
agents/incident_agent.py
------------------------
Parses & classifies the raw alert into a clean incident record and logs it to
the incident store (SQLite). Uses the small 8B model — extraction is cheap.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from configs.prompts import INCIDENT_PROMPT
from configs.settings import settings
from core.llm import chat_json
from graph.state import ResearchState
from monitoring.metrics import track_agent
from monitoring.logger import write_run_event


def _log_incident(incident: dict) -> None:
    try:
        con = sqlite3.connect(settings.sqlite_path)
        con.execute("""CREATE TABLE IF NOT EXISTS incidents(
            alert_id TEXT, category TEXT, severity TEXT, amount REAL,
            destination TEXT, summary TEXT, ts TEXT DEFAULT CURRENT_TIMESTAMP)""")
        con.execute("INSERT INTO incidents(alert_id,category,severity,amount,destination,summary)"
                    " VALUES (?,?,?,?,?,?)",
                    (incident.get("alert_id"), incident.get("category"),
                     incident.get("severity_hint"), float(incident.get("amount") or 0),
                     incident.get("destination"), incident.get("summary")))
        con.commit(); con.close()
    except Exception:
        pass


@track_agent("incident_agent")
def incident_node(state: ResearchState) -> dict:
    alert = state.get("alert", {})
    data, res = chat_json(INCIDENT_PROMPT, json.dumps(alert),
                          model=settings.model_small, max_tokens=400)

    # Always backfill from the raw alert so we never lose the amount/destination.
    incident = {
        "alert_id": data.get("alert_id") or alert.get("alert_id"),
        "category": data.get("category") or "other",
        "severity_hint": data.get("severity_hint") or "medium",
        "amount": data.get("amount") or alert.get("amount") or 0,
        "currency": data.get("currency") or alert.get("currency") or "INR",
        "destination": data.get("destination") or alert.get("destination") or "unknown",
        "signals": data.get("signals") or alert.get("signals") or [],
        "summary": data.get("summary") or f"Alert {alert.get('alert_id')} ingested.",
    }
    _log_incident(incident)
    write_run_event(state["run_id"], {"event": "incident.parsed", "level": "info",
                                      "category": incident["category"],
                                      "amount": incident["amount"]})
    done = state.get("done", []) + ["incident"]
    timeline = state.get("timeline", []) + [
        {"agent": "incident_agent", "detail": incident["summary"]}]
    return {"incident": incident, "done": done, "timeline": timeline,
            "_last_tokens": res.total_tokens}
