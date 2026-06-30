"""
app.py
------
Fraud Intelligence AI Assistant — analyst dashboard.

Tabs:
  1. Alerts        incoming alert inbox — the amount at risk is the hero
  2. Investigation run the agent pipeline, watch agents work, read the report
  3. Monitoring    three-pillar observability (metrics, RAGAS, guardrails)
  4. System        configuration, service map, knowledge base

API keys are read from .env via configs.settings — they are never entered here.
Launch:  streamlit run app.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import streamlit as st

import ui_kit as ui
from configs.settings import settings
from graph.workflow import run_pipeline
from graph import ragas_eval
from monitoring import metrics
from monitoring.tracer import langsmith_status
from core import store
from rag import ingestor

st.set_page_config(page_title="FIAA · Fraud Intelligence", page_icon="🛡️",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(ui.css(), unsafe_allow_html=True)

# Make sure the shared store exists (used to receive webhook-fired alerts).
store.init_db()

SAMPLE_PATH = Path(settings.data_dir) / "sample_alerts" / "alerts.json"


# ---------------------------------------------------------------- state ----
def _load_samples():
    try:
        return json.loads(SAMPLE_PATH.read_text())
    except Exception:
        return []


ss = st.session_state
ss.setdefault("inbox", _load_samples())
ss.setdefault("history", [])          # list of result dicts
ss.setdefault("active", None)         # current result dict
ss.setdefault("doc_text", None)
ss.setdefault("fired_ids", set())
ss.setdefault("seen_run_ids", set())  # run_ids already merged from the store
ss.setdefault("kb_msg", None)         # last knowledge-base refresh message


def _sync_from_store():
    """Pull any runs/alerts produced by the FastAPI webhook (a separate
    process) into this dashboard's session. This is what makes alerts fired
    via curl / Invoke-WebRequest appear here automatically."""
    # 1) new completed runs (newest first) -> history + active
    # Skip guardrail-blocked results: they carry no 'alert'/'report' (they were
    # stopped before the pipeline ran), so they must not enter the report UI.
    new_runs = []
    for r in store.latest_runs(50):
        rid = r.get("run_id")
        if rid and rid not in ss.seen_run_ids and not r.get("blocked") and r.get("report"):
            new_runs.append(r)
    # merge oldest-first so history stays newest-first overall
    for r in reversed(new_runs):
        ss.history.insert(0, r)
        ss.seen_run_ids.add(r["run_id"])
        ss.fired_ids.add((r.get("alert") or {}).get("alert_id"))
        ss.active = r  # surface the freshest webhook result

    # 2) inbound webhook alerts -> show them in the queue (dedup by alert_id)
    known = {a.get("alert_id") for a in ss.inbox}
    for a in store.inbox_alerts(50):
        if a.get("alert_id") not in known:
            ss.inbox.insert(0, a)
            known.add(a.get("alert_id"))
    return new_runs


_fresh = _sync_from_store()


def fire(alert: dict, live_steps: bool = True):
    """Run the pipeline for one alert and store the result."""
    steps = []
    if live_steps:
        with st.status(f"Investigating {alert.get('alert_id')}…", expanded=True) as status:
            box = st.empty()

            def cb(node, _state):
                steps.append(node)
                box.markdown(_render_steps(steps), unsafe_allow_html=True)

            result = run_pipeline(alert, document_text=ss.doc_text, on_event=cb)
            status.update(label=f"Investigation complete · {alert.get('alert_id')}",
                          state="complete")
    else:
        result = run_pipeline(alert, document_text=ss.doc_text)

    if not result.get("blocked"):
        ss.history.insert(0, result)
        ss.active = result
        ss.fired_ids.add(alert.get("alert_id"))
        ss.seen_run_ids.add(result.get("run_id"))
        store.save_run(result, source="dashboard")  # share with other process
    else:
        st.error(f"🛑 Blocked at guardrail: {result.get('reason')}")
        ss.active = result
    return result


def _render_steps(steps) -> str:
    names = {"incident": "Incident Agent — parse & classify",
             "supervisor": "Supervisor — route next agent",
             "search": "Search Agent — live web intelligence",
             "rag": "RAG Agent — retrieve precedent",
             "reader": "Reader Agent — extract document",
             "report": "Report Agent — synthesise report",
             "evaluator": "Evaluator — quality gate"}
    rows = ""
    for s in steps:
        rows += (f"<div class='step'><div class='dot'></div><div>"
                 f"<div class='who'>{names.get(s, s)}</div></div></div>")
    return rows


# --------------------------------------------------------------- sidebar ---
with st.sidebar:
    st.markdown(
        "<div class='fiaa-mast'><div class='fiaa-logo'>F</div>"
        "<div><div class='fiaa-title'>FIAA</div>"
        "<div class='fiaa-sub'>Fraud Intelligence</div></div></div>",
        unsafe_allow_html=True)
    st.markdown("<div class='small'>Autonomous fraud investigation · 90-second pipeline</div>",
                unsafe_allow_html=True)
    st.divider()

    # engine status
    mode = "DEMO (offline)" if settings.demo_mode else "LIVE (Groq)"
    mode_col = ui.AMBER if settings.demo_mode else ui.MINT
    st.markdown(f"<div class='small'>ENGINE</div>"
                f"<div style='font-weight:700;color:{mode_col};font-size:15px'>{mode}</div>",
                unsafe_allow_html=True)

    def dot(ok):
        return f"<span style='color:{ui.MINT if ok else ui.MUTED}'>●</span>"
    st.markdown(
        f"<div class='small' style='margin-top:10px;line-height:1.9'>"
        f"{dot(settings.has_groq)} Groq LLM &nbsp; "
        f"{dot(settings.has_tavily)} Tavily web<br>"
        f"{dot(settings.has_langsmith)} LangSmith &nbsp; "
        f"{dot(True)} ChromaDB</div>", unsafe_allow_html=True)
    st.divider()

    st.markdown("<div class='small'>WEBHOOK FEED</div>", unsafe_allow_html=True)
    live = st.toggle("Live (auto-refresh)", value=True,
                     help="Poll the shared store so alerts POSTed to the "
                          "/api/analyse webhook appear here automatically.")
    if st.button("🔄 Check for new alerts", use_container_width=True):
        st.rerun()
    st.divider()

    st.markdown("<div class='small'>TRIGGER MODE</div>", unsafe_allow_html=True)
    trig = st.radio("trigger", ["Manual", "Timer · 60s", "Random · 45s"],
                    label_visibility="collapsed")

    if st.button("⚡ Fire next alert", use_container_width=True):
        pool = [a for a in ss.inbox if a["alert_id"] not in ss.fired_ids] or ss.inbox
        fire(pool[0])

    st.divider()
    st.markdown("<div class='small'>KYC / STATEMENT (optional)</div>", unsafe_allow_html=True)
    up = st.file_uploader("pdf", type=["pdf"], label_visibility="collapsed")
    if up is not None:
        from agents.reader_agent import extract_pdf_text
        ss.doc_text = extract_pdf_text(up.read())
        st.caption(f"📎 {up.name} attached · {len(ss.doc_text or '')} chars")

    if ss.history:
        st.divider()
        st.markdown("<div class='small'>RUN HISTORY</div>", unsafe_allow_html=True)
        labels = [f"{(r.get('alert') or {}).get('alert_id', r.get('run_id','run'))}"
                  f" · {(r.get('report') or {}).get('risk_score','?')}"
                  for r in ss.history]
        pick = st.selectbox("history", range(len(labels)),
                            format_func=lambda i: labels[i], label_visibility="collapsed")
        if st.button("Open run", use_container_width=True):
            ss.active = ss.history[pick]


# --------------------------------------------------------------- masthead --
st.markdown(
    "<div class='fiaa-mast'><div class='fiaa-logo'>🛡️</div>"
    "<div><div class='fiaa-title'>Fraud Intelligence AI Assistant</div>"
    "<div class='fiaa-sub'>LangGraph · Groq · ChromaDB · Tavily · LangSmith</div>"
    "</div></div>", unsafe_allow_html=True)

if settings.demo_mode:
    st.info("Running in **demo mode** — no GROQ_API_KEY found in `.env`. The full "
            "pipeline still runs with an offline engine. Add keys to `.env` for live LLM, "
            "web search and tracing.", icon="🔌")

if _fresh:
    ids = ", ".join((r.get("alert") or {}).get("alert_id", "?") for r in _fresh)
    st.success(f"📥 {len(_fresh)} new alert(s) received via webhook: {ids} — "
               "opened in the Investigation tab.", icon="📡")

tab_alerts, tab_inv, tab_review, tab_resolved, tab_mon, tab_sys = st.tabs(
    ["🚨  Alerts", "🔬  Investigation", "🧑‍⚖️  Review Queue", "✅  Resolved",
     "📈  Monitoring", "⚙️  System"])


# Outcome labels/colours shared by Review Queue and Resolved tabs.
OUTCOME_META = {
    "confirmed_fraud": ("CONFIRMED FRAUD", ui.CRIMSON),
    "false_positive":  ("FALSE POSITIVE", ui.MINT),
    "escalated":       ("ESCALATED", ui.AMBER),
    "auto_closed":     ("AUTO-CLOSED", ui.MINT),
}


def case_status(r: dict, actions: dict):
    """Effective status of a run: ('resolved'|'pending_review'|'auto_closed', action).
    An analyst verdict (in `actions`) overrides the AI's decision."""
    act = actions.get(r.get("run_id"))
    if act and act.get("status") in ("resolved", "escalated"):
        return "resolved", act
    if r.get("decision") in ("human_review", "reinvestigate"):
        return "pending_review", {}
    return "auto_closed", {}


# ============================================================ TAB 1: ALERTS
with tab_alerts:
    # Hero = the most recent / selected alert with the amount as the headline
    hero = (ss.active or {}).get("alert") if ss.active else (ss.inbox[0] if ss.inbox else None)
    if hero:
        sig = hero.get("signals", [])
        hot = any(s in sig for s in ("velocity_breach", "geo_anomaly", "high_value"))
        strip = ui.CRIMSON if hot else ui.AMBER
        chips = "".join(
            f"<span class='chip {'hot' if s in ('velocity_breach','geo_anomaly','high_value') else 'warn'}'>"
            f"{s.replace('_',' ')}</span>" for s in sig)
        st.markdown(f"""
        <div class='hero'>
          <div class='strip' style='background:{strip}'></div>
          <div class='kicker'>Amount at risk · {hero.get('channel','wire').upper()} · alert {hero.get('alert_id')}</div>
          <div class='amount' style='margin-top:8px'>
            <span class='cur'>{hero.get('currency','INR')}</span>{ui.inr(hero.get('amount'))}
          </div>
          <div class='meta-grid'>
            <div><div class='lbl'>Account</div><div class='val'>{hero.get('account','—')}</div></div>
            <div><div class='lbl'>Destination</div><div class='val'>{hero.get('destination','—')}</div></div>
            <div><div class='lbl'>SLA window</div><div class='val'>{hero.get('sla_minutes','—')} min</div></div>
          </div>
          <div style='margin-top:16px'>{chips}</div>
        </div>""", unsafe_allow_html=True)

        c1, c2 = st.columns([1, 3])
        with c1:
            if st.button("🔬 Investigate this alert", use_container_width=True):
                fire(hero)
        with c2:
            st.caption("Firing runs the full multi-agent pipeline and opens the Investigation tab’s report.")

    st.markdown("<div class='kicker' style='margin:22px 0 10px'>Incoming alert queue</div>",
                unsafe_allow_html=True)

    # Pending = alerts not yet investigated. Once investigated, an alert leaves
    # the queue and moves to the Resolved table below.
    pending = [a for a in ss.inbox if a.get("alert_id") not in ss.fired_ids]
    if not pending:
        st.markdown("<div class='panel'><div class='small'>Queue is clear — all "
                    "incoming alerts have been investigated. See the resolved table "
                    "below.</div></div>", unsafe_allow_html=True)

    for a in pending:
        sig = a.get("signals", [])
        hot = any(s in sig for s in ("velocity_breach", "geo_anomaly", "high_value"))
        amt_col = ui.CRIMSON if hot else ui.TEXT
        cols = st.columns([2.2, 2, 2, 1.4, 1.2])
        cols[0].markdown(
            f"<div class='alert-id'>{a['alert_id']}</div>"
            f"<div class='alert-amt' style='color:{amt_col}'>₹{ui.inr(a['amount'])}</div>",
            unsafe_allow_html=True)
        cols[1].markdown(f"<div class='small'>Destination</div>"
                         f"<div style='font-weight:600'>{a.get('destination','—')}</div>",
                         unsafe_allow_html=True)
        cols[2].markdown(
            "<div class='small'>Signals</div>"
            f"<div style='font-weight:600'>{len(sig)} · {sig[0].replace('_',' ') if sig else '—'}</div>",
            unsafe_allow_html=True)
        cols[3].markdown(f"<div class='small'>SLA</div>"
                         f"<div style='font-weight:600'>{a.get('sla_minutes')}m</div>",
                         unsafe_allow_html=True)
        if cols[4].button("Run", key=f"run_{a['alert_id']}", use_container_width=True):
            fire(a)

    st.caption("Investigated alerts move to the **Review Queue** (if escalated to human "
               "review) or the **Resolved** tab.")


# ===================================================== TAB 2: INVESTIGATION
with tab_inv:
    res = ss.active
    if not res:
        st.markdown("<div class='panel'>No investigation yet. Fire an alert from the "
                    "<b>Alerts</b> tab or the sidebar to generate a report.</div>",
                    unsafe_allow_html=True)
    elif res.get("blocked"):
        st.error(f"🛑 This alert was blocked at the input guardrail: **{res.get('reason')}** "
                 f"(flags: {', '.join(res.get('flags', [])) or 'none'})")
    else:
        rep = res["report"]
        score = float(rep.get("risk_score", 5.0))
        label, colour = ui.risk_band(score)
        decision = res["decision"]
        dbadge = {"human_review": ("hi", "Human review"),
                  "auto_close": ("lo", "Auto close"),
                  "reinvestigate": ("re", "Reinvestigate")}[decision]

        left, right = st.columns([1, 2.1])
        with left:
            st.markdown(f"<div class='panel' style='text-align:center'>"
                        f"{ui.gauge_svg(score)}"
                        f"<div style='margin-top:6px'><span class='badge {dbadge[0]}'>"
                        f"{dbadge[1]}</span></div>"
                        f"<div class='small' style='margin-top:10px'>"
                        f"run {res['run_id']} · {res['duration_s']}s · "
                        f"{res['iterations']} iterations · {res['total_tokens']} tokens</div>"
                        f"</div>", unsafe_allow_html=True)
        with right:
            st.markdown(
                f"<div class='panel'><div class='kicker'>{label} RISK · "
                f"confidence {rep.get('confidence','—')}</div>"
                f"<div style='font-size:20px;font-weight:700;margin:6px 0 8px'>"
                f"{rep.get('headline','—')}</div>"
                f"<div class='small' style='font-size:13.5px;line-height:1.6'>"
                f"{rep.get('narrative','')}</div>"
                f"<div class='small' style='margin-top:12px'><b style='color:{colour}'>Why this score:</b> "
                f"{rep.get('risk_rationale','')}</div></div>", unsafe_allow_html=True)

        # evidence
        st.markdown("<div class='kicker' style='margin:10px 0 8px'>Evidence</div>",
                    unsafe_allow_html=True)
        ev_html = "<div class='panel'>"
        for e in rep.get("evidence", []):
            w = str(e.get("weight", "low")).lower()
            ev_html += (f"<div class='ev {w}'><div>{e.get('finding','')}</div>"
                        f"<div class='src'>{e.get('source','?')} · {w} weight</div></div>")
        ev_html += "</div>"
        st.markdown(ev_html, unsafe_allow_html=True)

        a, b = st.columns(2)
        with a:
            reg = rep.get("regulatory", {}) or {}
            dl = reg.get("deadline_minutes")
            st.markdown(
                "<div class='panel'><div class='kicker'>Regulatory</div>"
                + "".join(f"<div style='margin-top:6px'>• {r}</div>"
                          for r in (reg.get("applies") or ["None identified"]))
                + (f"<div style='margin-top:10px;color:{ui.CRIMSON};font-weight:700'>"
                   f"⏱ Deadline: {dl} min</div>" if dl else "")
                + "</div>", unsafe_allow_html=True)
        with b:
            st.markdown(
                "<div class='panel'><div class='kicker'>Recommended actions</div>"
                + "".join(f"<div style='margin-top:6px'>→ {x}</div>"
                          for x in rep.get("recommended_actions", []))
                + "</div>", unsafe_allow_html=True)

        # CRIS draft
        st.markdown(
            "<div class='panel'><div class='kicker'>CRIS draft · regulator-ready summary</div>"
            f"<div class='small' style='font-size:13.5px;line-height:1.6;margin-top:8px'>"
            f"{rep.get('cris_draft','')}</div></div>", unsafe_allow_html=True)

        # evaluator + ragas + guardrails
        ev = res.get("evaluation", {})
        rg = res.get("ragas", {})
        g, h, i = st.columns(3)
        g.markdown(
            "<div class='tile'><div class='cap'>Evaluator</div>"
            f"<div class='big' style='color:{ui.MINT if ev.get('approved') else ui.AMBER}'>"
            f"{'PASS' if ev.get('approved') else 'REVISE'}</div>"
            f"<div class='small'>quality {ev.get('score','—')}</div></div>",
            unsafe_allow_html=True)
        h.markdown(
            "<div class='tile'><div class='cap'>RAGAS faithfulness</div>"
            f"<div class='big'>{rg.get('faithfulness','—')}</div>"
            f"<div class='small'>relevance {rg.get('answer_relevance','—')} · "
            f"recall {rg.get('context_recall','—')}</div></div>", unsafe_allow_html=True)
        flags = res.get("output_flags", [])
        i.markdown(
            "<div class='tile'><div class='cap'>Output guardrails</div>"
            f"<div class='big' style='color:{ui.MINT if not flags else ui.AMBER}'>"
            f"{'CLEAN' if not flags else str(len(flags))}</div>"
            f"<div class='small'>{', '.join(flags) if flags else 'no flags'}</div></div>",
            unsafe_allow_html=True)

        if res.get("guardrail_notes"):
            st.caption("🔒 " + " · ".join(res["guardrail_notes"]))

        # agent timeline + download
        with st.expander("Agent timeline & raw report"):
            for t in res.get("timeline", []):
                st.markdown(f"<div class='step'><div class='dot'></div><div>"
                            f"<div class='who'>{t['agent']}</div>"
                            f"<div class='what'>{t.get('detail','')}</div></div></div>",
                            unsafe_allow_html=True)
            st.json(rep)

        st.download_button(
            "⬇ Download report (JSON)",
            data=json.dumps(res, indent=2, default=str),
            file_name=f"fiaa_report_{res['run_id']}.json",
            mime="application/json")


# ===================================================== TAB: REVIEW QUEUE
with tab_review:
    actions = store.all_case_actions()
    pending = [r for r in ss.history if case_status(r, actions)[0] == "pending_review"]

    st.markdown("<div class='kicker' style='margin-bottom:6px'>Cases awaiting analyst "
                "decision · risk ≥ 7 escalated by the AI</div>", unsafe_allow_html=True)
    analyst_name = st.text_input("Analyst", value=ss.get("analyst_name", "analyst"),
                                 key="analyst_name",
                                 help="Recorded against every decision for the audit trail.")

    if not pending:
        st.markdown("<div class='panel small'>No cases awaiting review. High-risk "
                    "investigations (risk ≥ 7) appear here for an analyst to confirm fraud, "
                    "mark a false positive, or escalate.</div>", unsafe_allow_html=True)

    for r in pending:
        al = r.get("alert") or {}
        rep = r.get("report") or {}
        rid = r.get("run_id")
        score = rep.get("risk_score", "?")
        st.markdown(
            f"<div class='panel'><div style='display:flex;justify-content:space-between'>"
            f"<div><span class='alert-id'>{al.get('alert_id','—')}</span> "
            f"<span class='small'>· ₹{ui.inr(al.get('amount',0))} → "
            f"{al.get('destination','—')}</span></div>"
            f"<div style='font-weight:800;color:{ui.CRIMSON}'>RISK {score}</div></div>"
            f"<div class='small' style='margin-top:6px'>{rep.get('headline','')}</div>"
            "</div>", unsafe_allow_html=True)
        notes = st.text_input("Decision notes (why)", key=f"notes_{rid}",
                              placeholder="e.g. Verified property sale, sale deed on file, "
                                          "customer confirmed by phone")
        b1, b2, b3, b4 = st.columns(4)
        if b1.button("✅ Confirm fraud", key=f"cf_{rid}", use_container_width=True):
            store.set_case_action(rid, "resolved", "confirmed_fraud",
                                  analyst_name, notes, al.get("alert_id", ""))
            st.rerun()
        if b2.button("⚠️ False positive", key=f"fp_{rid}", use_container_width=True):
            store.set_case_action(rid, "resolved", "false_positive",
                                  analyst_name, notes, al.get("alert_id", ""))
            st.rerun()
        if b3.button("⬆️ Escalate", key=f"esc_{rid}", use_container_width=True):
            store.set_case_action(rid, "escalated", "escalated",
                                  analyst_name, notes, al.get("alert_id", ""))
            st.rerun()
        if b4.button("🔬 Open report", key=f"openr_{rid}", use_container_width=True):
            ss.active = r
            st.rerun()


# ===================================================== TAB: RESOLVED
with tab_resolved:
    actions = store.all_case_actions()
    resolved = []
    for r in ss.history:
        st_, act = case_status(r, actions)
        if st_ in ("resolved", "auto_closed"):
            resolved.append((r, act))

    st.markdown("<div class='kicker' style='margin-bottom:10px'>Concluded cases · "
                "outcome, analyst and time recorded (audit trail)</div>",
                unsafe_allow_html=True)

    if not resolved:
        st.markdown("<div class='panel small'>No resolved cases yet. Auto-closed alerts "
                    "and analyst-decided cases appear here.</div>", unsafe_allow_html=True)

    hc = st.columns([2, 1.6, 0.9, 1.7, 1.6, 1.1])
    for col, txt in zip(hc, ["ALERT", "DESTINATION", "RISK", "OUTCOME", "ANALYST", ""]):
        col.markdown(f"<div class='small' style='letter-spacing:.5px'>{txt}</div>",
                     unsafe_allow_html=True)

    for r, act in resolved:
        al = r.get("alert") or {}
        rep = r.get("report") or {}
        outcome = act.get("outcome") if act else "auto_closed"
        label, col = OUTCOME_META.get(outcome, (str(outcome).upper(), ui.MUTED))
        analyst = act.get("analyst") if act else "system (AI)"
        rid = r.get("run_id")
        rc = st.columns([2, 1.6, 0.9, 1.7, 1.6, 1.1])
        rc[0].markdown(f"<div class='alert-id'>{al.get('alert_id','—')}</div>"
                       f"<div class='small'>₹{ui.inr(al.get('amount',0))}</div>",
                       unsafe_allow_html=True)
        rc[1].markdown(f"<div style='padding-top:6px'>{al.get('destination','—')}</div>",
                       unsafe_allow_html=True)
        rc[2].markdown(f"<div style='font-weight:700;padding-top:6px'>"
                       f"{rep.get('risk_score','?')}</div>", unsafe_allow_html=True)
        rc[3].markdown(f"<div style='font-weight:800;color:{col};padding-top:6px'>"
                       f"{label}</div>", unsafe_allow_html=True)
        rc[4].markdown(f"<div class='small' style='padding-top:6px'>{analyst}</div>",
                       unsafe_allow_html=True)
        if rc[5].button("Open", key=f"ropen_{rid}", use_container_width=True):
            ss.active = r
            st.rerun()
        if act and act.get("notes"):
            st.caption(f"📝 {al.get('alert_id','')}: {act['notes']}")
        memo = (f"CASE MEMO · {al.get('alert_id','')}\n"
                f"Outcome: {label}  |  Analyst: {analyst}\n"
                f"Risk score: {rep.get('risk_score','?')}\n\n"
                f"{rep.get('cris_draft','')}\n\n"
                f"Recommended actions:\n- " +
                "\n- ".join(rep.get("recommended_actions", []) or ["—"]))
        st.download_button("⬇ Export case memo (CRIS)", data=memo,
                           file_name=f"case_memo_{al.get('alert_id','run')}.txt",
                           mime="text/plain", key=f"memo_{rid}")


# ======================================================= TAB 3: MONITORING
with tab_mon:
    snap = metrics.snapshot()

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0.0

    total_calls = sum(v.get("success", 0) + v.get("error", 0)
                      for v in snap["agent_calls"].values())
    errs = sum(v.get("error", 0) for v in snap["agent_calls"].values())
    err_rate = (errs / total_calls * 100) if total_calls else 0.0

    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(f"<div class='tile'><div class='cap'>Agent calls</div>"
                f"<div class='big'>{total_calls}</div></div>", unsafe_allow_html=True)
    k2.markdown(f"<div class='tile'><div class='cap'>Error rate</div>"
                f"<div class='big' style='color:{ui.CRIMSON if err_rate>10 else ui.MINT}'>"
                f"{err_rate:.0f}%</div></div>", unsafe_allow_html=True)
    k3.markdown(f"<div class='tile'><div class='cap'>Last risk score</div>"
                f"<div class='big'>{snap['last_risk_score']:.1f}</div></div>",
                unsafe_allow_html=True)
    k4.markdown(f"<div class='tile'><div class='cap'>Active runs</div>"
                f"<div class='big'>{snap['active_runs']}</div></div>",
                unsafe_allow_html=True)

    st.markdown("<div class='kicker' style='margin:18px 0 8px'>Agent latency (avg seconds)</div>",
                unsafe_allow_html=True)
    lat = snap["agent_latency"]
    if lat:
        mx = max(avg(v) for v in lat.values()) or 1
        rows = "<div class='panel'>"
        for agent, vals in lat.items():
            a = avg(vals)
            pct = int(a / mx * 100)
            col = ui.CRIMSON if (agent == "report_agent" and a > 30) else ui.CYAN
            rows += (f"<div style='margin-bottom:12px'>"
                     f"<div style='display:flex;justify-content:space-between'>"
                     f"<span class='small'>{agent}</span>"
                     f"<span class='small'>{a:.2f}s · {len(vals)} calls</span></div>"
                     f"<div class='bar-wrap'><div class='bar' "
                     f"style='width:{pct}%;background:{col}'></div></div></div>")
        rows += "</div>"
        st.markdown(rows, unsafe_allow_html=True)
    else:
        st.markdown("<div class='panel small'>No agent calls yet — fire an alert.</div>",
                    unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='kicker' style='margin:6px 0 8px'>Token cost per agent</div>",
                    unsafe_allow_html=True)
        tok = snap["agent_tokens"]
        body = "<div class='panel'>"
        if tok:
            for agent, vals in tok.items():
                body += (f"<div style='display:flex;justify-content:space-between'>"
                         f"<span class='small'>{agent}</span>"
                         f"<span style='font-family:JetBrains Mono'>{int(sum(vals))}</span></div>")
        else:
            body += "<span class='small'>—</span>"
        st.markdown(body + "</div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='kicker' style='margin:6px 0 8px'>Guardrail hits</div>",
                    unsafe_allow_html=True)
        gh = snap["guardrail_hits"]
        body = "<div class='panel'>"
        if gh:
            for t, n in gh.items():
                col = ui.CRIMSON if t in ("injection", "hallucination") else ui.AMBER
                body += (f"<div style='display:flex;justify-content:space-between'>"
                         f"<span class='small' style='color:{col}'>{t}</span>"
                         f"<span style='font-family:JetBrains Mono'>{n}</span></div>")
        else:
            body += "<span class='small'>none — clean</span>"
        st.markdown(body + "</div>", unsafe_allow_html=True)

    st.markdown("<div class='kicker' style='margin:18px 0 8px'>RAGAS trend (recent runs)</div>",
                unsafe_allow_html=True)
    rr = ragas_eval.recent(12)
    if rr:
        import pandas as pd
        df = pd.DataFrame(rr)[["faithfulness", "answer_relevance", "context_recall"]][::-1]
        st.line_chart(df, height=220)
        low = [r for r in rr[:3] if r["faithfulness"] < 0.7]
        if len(low) >= 3:
            st.warning("⚠ RAGAS faithfulness < 0.7 for 3 consecutive runs — knowledge base "
                       "may need a refresh.")
    else:
        st.markdown("<div class='panel small'>No RAGAS scores yet.</div>",
                    unsafe_allow_html=True)
    st.caption(f"Prometheus → :{settings.metrics_port}/metrics · Grafana → :3000 · "
               f"LangSmith → {langsmith_status()}")


# =========================================================== TAB 4: SYSTEM
with tab_sys:
    st.markdown("<div class='kicker' style='margin-bottom:8px'>Configuration "
                "(read from .env — never from this UI)</div>", unsafe_allow_html=True)
    cfg = {
        "Environment": settings.env,
        "Engine mode": "demo (offline)" if settings.demo_mode else "live",
        "Report model": settings.model_report,
        "Fallback chain": " → ".join(settings.model_chain),
        "Embedding model": settings.embed_model,
        "RAG top-k": settings.rag_top_k,
        "Iteration cap": settings.iteration_cap,
        "High-risk threshold": settings.high_risk_threshold,
        "Webhook port": settings.api_port,
        "Metrics port": settings.metrics_port,
    }
    rows = "<div class='panel'>"
    for k, v in cfg.items():
        rows += (f"<div style='display:flex;justify-content:space-between;padding:5px 0;"
                 f"border-bottom:1px solid {ui.LINE}'>"
                 f"<span class='small'>{k}</span>"
                 f"<span style='font-family:JetBrains Mono;font-size:13px'>{v}</span></div>")
    st.markdown(rows + "</div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<div class='panel'><div class='kicker'>Service map</div>"
                    "<div class='small' style='line-height:2;margin-top:6px'>"
                    "🖥 Streamlit UI · :8501<br>"
                    "🔗 FastAPI webhook · :8001/api/analyse<br>"
                    "📘 Swagger docs · :8001/docs<br>"
                    "📊 Metrics · :8000/metrics<br>"
                    "📈 Grafana · :3000<br>"
                    "🧬 ChromaDB · :8002<br>"
                    "🛰 LangSmith · smith.langchain.com</div></div>",
                    unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='panel'><div class='kicker'>Three-pillar observability</div>"
                    "<div class='small' style='line-height:1.9;margin-top:6px'>"
                    "<b>Logging</b> — structlog JSON, run_id bound, secrets redacted<br>"
                    "<b>Metrics</b> — Prometheus 8 metrics → Grafana<br>"
                    "<b>Tracing</b> — LangSmith chain replay + OTel spans<br><br>"
                    "Every agent passes through <code>@track_agent</code> — zero monitoring "
                    "code lives inside the agents.</div></div>", unsafe_allow_html=True)

    # knowledge base — live stats + one-click refresh
    kb_stats = ingestor.stats()
    if ss.kb_msg:
        (st.success if ss.kb_msg.get("ok") else st.warning)(ss.kb_msg["message"])
        ss.kb_msg = None

    kc1, kc2 = st.columns([3, 1])
    with kc1:
        st.markdown(
            "<div class='panel'><div class='kicker'>Knowledge base</div>"
            f"<div class='small' style='margin-top:6px;line-height:1.9'>"
            f"Backend: <b>{kb_stats['backend']}</b><br>"
            f"Indexed vectors: <b>{kb_stats['indexed_chunks']}</b> · "
            f"Source chunks: <b>{kb_stats['source_documents']}</b><br>"
            f"Past cases: <b>{kb_stats['past_cases']}</b> · "
            f"Collection: <code>{kb_stats['collection']}</code><br>"
            f"CLI rebuild: <code>python -m rag.ingestor</code></div></div>",
            unsafe_allow_html=True)
    with kc2:
        st.markdown("<div class='small'>&nbsp;</div>", unsafe_allow_html=True)
        if st.button("🔄 Refresh knowledge base", use_container_width=True):
            with st.spinner("Re-embedding documents into ChromaDB…"):
                ss.kb_msg = ingestor.refresh()
            st.rerun()


# --------------------------------------------------- live webhook poller ---
# When "Live" is on, poll the shared store every few seconds. If the FastAPI
# webhook produced a new run (from a different process), trigger a full rerun
# so _sync_from_store() at the top of the script pulls it in.
if live:
    @st.fragment(run_every="3s")
    def _poller():
        newest = store.latest_run_id()
        if newest and newest not in ss.seen_run_ids:
            st.rerun()
    _poller()


# --------------------------------------------------------- auto-trigger ----
# Timer / Random modes auto-fire sample alerts for hands-free demos.
if trig != "Manual":
    interval = "60s" if trig.startswith("Timer") else "45s"

    @st.fragment(run_every=interval)
    def _autopilot():
        st.caption(f"🛰 Auto-pilot active ({trig}) — firing alerts automatically…")
        pool = [a for a in ss.inbox if a["alert_id"] not in ss.fired_ids] or ss.inbox
        if not pool:
            return
        choice = pool[0] if trig.startswith("Timer") else random.choice(pool)
        result = run_pipeline(choice, document_text=ss.doc_text)
        if not result.get("blocked"):
            store.save_run(result, source="autopilot")
            st.rerun()  # full rerun -> store sync merges it everywhere

    _autopilot()
