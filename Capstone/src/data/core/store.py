"""
core/store.py
-------------


This module gives both processes ONE place on disk to read and write:

  * runs          — every completed investigation (full JSON result)
  * webhook_inbox — every alert received over the webhook, so the dashboard
                    can show it in the queue the moment it arrives

SQLite is used in WAL mode with a busy timeout so two processes can read and
write at the same time without "database is locked" errors. No external
service is needed — it is just a file (settings.sqlite_path).
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Dict, List, Optional

from configs.settings import settings


# --------------------------------------------------------------------------
# connection helper
# --------------------------------------------------------------------------
def _connect() -> sqlite3.Connection:
    # timeout lets a writer wait instead of failing if another process is busy.
    con = sqlite3.connect(settings.sqlite_path, timeout=10)
    con.row_factory = sqlite3.Row
    # WAL = many readers + one writer concurrently (perfect for our 2 processes)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    return con


def init_db() -> None:
    """Create tables once. Safe to call repeatedly (idempotent)."""
    con = _connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS runs(
            run_id      TEXT PRIMARY KEY,
            alert_id    TEXT,
            ts          REAL,
            risk_score  REAL,
            decision    TEXT,
            source      TEXT,
            payload     TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS webhook_inbox(
            alert_id    TEXT PRIMARY KEY,
            ts          REAL,
            status      TEXT,
            payload     TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS case_actions(
            run_id      TEXT PRIMARY KEY,
            alert_id    TEXT,
            status      TEXT,
            outcome     TEXT,
            analyst     TEXT,
            notes       TEXT,
            resolved_ts REAL
        )"""
    )
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# runs  (completed investigations)
# --------------------------------------------------------------------------
def save_run(result: Dict, source: str = "dashboard") -> None:
    """Persist one completed pipeline result so any process can read it."""
    if not result or not result.get("run_id"):
        return
    init_db()
    con = _connect()
    con.execute(
        "INSERT OR REPLACE INTO runs"
        "(run_id, alert_id, ts, risk_score, decision, source, payload)"
        " VALUES (?,?,?,?,?,?,?)",
        (
            result["run_id"],
            (result.get("alert") or {}).get("alert_id"),
            time.time(),
            float((result.get("report") or {}).get("risk_score", 0) or 0),
            result.get("decision", ""),
            source,
            json.dumps(result, default=str),
        ),
    )
    con.commit()
    con.close()


def get_run(run_id: str) -> Optional[Dict]:
    init_db()
    con = _connect()
    row = con.execute("SELECT payload FROM runs WHERE run_id=?", (run_id,)).fetchone()
    con.close()
    return json.loads(row["payload"]) if row else None


def latest_runs(limit: int = 50) -> List[Dict]:
    """Most recent completed runs, newest first (full result dicts)."""
    init_db()
    con = _connect()
    rows = con.execute(
        "SELECT payload FROM runs ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        try:
            out.append(json.loads(r["payload"]))
        except Exception:
            continue
    return out


def latest_run_id() -> Optional[str]:
    """Newest run_id only — cheap call the dashboard polls to detect new work."""
    init_db()
    con = _connect()
    row = con.execute("SELECT run_id FROM runs ORDER BY ts DESC LIMIT 1").fetchone()
    con.close()
    return row["run_id"] if row else None


# --------------------------------------------------------------------------
# webhook inbox  (alerts received over the wire)
# --------------------------------------------------------------------------
def enqueue_inbox_alert(alert: Dict, status: str = "processing") -> None:
    """Record an inbound webhook alert so the dashboard queue shows it live."""
    if not alert or not alert.get("alert_id"):
        return
    init_db()
    con = _connect()
    con.execute(
        "INSERT OR REPLACE INTO webhook_inbox(alert_id, ts, status, payload)"
        " VALUES (?,?,?,?)",
        (alert["alert_id"], time.time(), status, json.dumps(alert, default=str)),
    )
    con.commit()
    con.close()


def set_inbox_status(alert_id: str, status: str) -> None:
    init_db()
    con = _connect()
    con.execute("UPDATE webhook_inbox SET status=? WHERE alert_id=?", (status, alert_id))
    con.commit()
    con.close()


def inbox_alerts(limit: int = 50) -> List[Dict]:
    """Inbound webhook alerts, newest first. Each carries a `_status` field."""
    init_db()
    con = _connect()
    rows = con.execute(
        "SELECT payload, status FROM webhook_inbox ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        try:
            a = json.loads(r["payload"])
            a["_status"] = r["status"]
            out.append(a)
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------
# case lifecycle  (analyst verdict on human-review cases) — audit trail
# --------------------------------------------------------------------------
def set_case_action(run_id: str, status: str, outcome: str = "",
                    analyst: str = "", notes: str = "", alert_id: str = "") -> None:
    """Record (or update) an analyst's verdict on a case."""
    if not run_id:
        return
    init_db()
    con = _connect()
    con.execute(
        "INSERT OR REPLACE INTO case_actions"
        "(run_id, alert_id, status, outcome, analyst, notes, resolved_ts)"
        " VALUES (?,?,?,?,?,?,?)",
        (run_id, alert_id, status, outcome, analyst, notes, time.time()),
    )
    con.commit()
    con.close()


def get_case_action(run_id: str) -> Optional[Dict]:
    init_db()
    con = _connect()
    row = con.execute("SELECT * FROM case_actions WHERE run_id=?", (run_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def all_case_actions(limit: int = 200) -> Dict[str, Dict]:
    """Map of run_id -> action row, used to overlay status onto runs."""
    init_db()
    con = _connect()
    rows = con.execute(
        "SELECT * FROM case_actions ORDER BY resolved_ts DESC LIMIT ?", (limit,)
    ).fetchall()
    con.close()
    return {r["run_id"]: dict(r) for r in rows}
