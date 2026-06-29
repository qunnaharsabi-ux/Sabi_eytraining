# FIAA — Fraud Intelligence AI Assistant

A multi-agent fraud-investigation system that turns a raw bank fraud alert into a
fully-evidenced, regulator-ready investigation report in seconds — work that
takes a human analyst 45–90 minutes. Built with **LangGraph**, **Groq (Llama 3.3
70B)**, **ChromaDB**, **Tavily**, **LangSmith**, **Prometheus/Grafana** and a
custom **Streamlit** command-centre dashboard.

> **Runs with zero API keys.** Leave `.env` blank and the whole pipeline runs in
> **DEMO MODE** with realistic synthetic output, so you can see the dashboard and
> a full investigation immediately. Add a Groq key for live LLM reasoning.


## What it does

A bank rule engine POSTs a suspicious transaction to the webhook. A **Supervisor**
agent then orchestrates four research agents in a hub-and-spoke graph:

| Agent | Job |
|-------|-----|
| **Incident** | Parses & classifies the alert, logs it to the incident DB |
| **Search** | Tavily live web — fraud patterns, RBI circulars, SWIFT advisories |
| **RAG** | ChromaDB cosine search — top-5 past cases, playbooks, RBI guidelines |
| **Reader** | PyMuPDF — extracts text from uploaded KYC PDFs / statements |

Findings converge into the **Report** agent (Llama 3.3 70B), which produces a
risk score (1–10), an evidence table, a regulatory/CRIS draft and recommended
actions. An **Evaluator** + **RAGAS** quality gate checks the report for evidence
grounding, score proportionality, PII leakage and citation accuracy. Score ≥ 7
→ human review; < 7 → auto-close.

Every agent call flows through one `@track_agent` decorator that emits to all
three observability pillars at once — **structlog** (JSON logs, run_id bound,
secrets redacted), **Prometheus** (8 `fiaa_*` metrics), and **LangSmith + OTel**
(chain traces).

---

## The dashboard (4 tabs)

1. **🚨 Alerts** — the incoming-alert inbox. The **amount at risk is the hero**:
   a large monospaced figure in Indian grouping (e.g. `₹4,87,000`), with account,
   destination, SLA window and the triggering signals. Fire an investigation
   manually, on a 60s timer, or randomly every 45s.
2. **🔬 Investigation** — animated SVG risk gauge + the full report: headline,
   narrative, evidence table, regulatory draft, actions, CRIS, evaluator verdict,
   RAGAS scores, guardrail audit. One-click report download.
3. **📈 Monitoring** — live metric tiles, agent latency bars, token usage,
   guardrail hits, and a RAGAS trend chart (mirrors the Grafana board).
4. **⚙️ System** — config, service map, observability status, knowledge-base stats.

**API keys are only ever read from `.env`** — the UI can never set a key.

---

## Quick start (no Docker)

```bash
# 1. configure (optional — blank keys => DEMO MODE)
cp .env.example .env          # then paste your GROQ_API_KEY if you have one

# 2. install
pip install -r requirements.txt

# 3. build the RAG knowledge base into ChromaDB
#    (optional — the app also auto-builds it the first time it is queried,
#     and the System tab has a "Refresh knowledge base" button)
python -m rag.ingestor

# 4a. dashboard only
streamlit run app.py
#     -> http://localhost:8501

# 4b. OR full stack (dashboard + FastAPI webhook + metrics) — use this if you
#     want to POST alerts to the webhook and watch them appear on the dashboard
python start.py
#     dashboard  http://localhost:8501
#     webhook    http://localhost:8001/api/analyse
#     metrics    http://localhost:8000/metrics
```

Fire a test alert at the webhook:

```bash
curl -X POST http://localhost:8001/api/analyse \
  -H "Content-Type: application/json" \
  -H "X-API-Key: fiaa-secret-key-2025" \
  -d '{"alert_id":"FR-2025-8821","account":"****4729","amount":487000,
       "destination":"Cayman Islands",
       "signals":["velocity_breach","geo_anomaly","new_device"],
       "sla_minutes":120}'
```

On **Windows PowerShell** use `Invoke-RestMethod` (cleaner than `Invoke-WebRequest`
for JSON). Note the `X-API-Key` header — without it you get a 401:

```powershell
$body = @{
  alert_id    = "FR-2025-8821"
  account     = "****4729"
  amount      = 487000
  currency    = "INR"
  destination = "Cayman Islands"
  signals     = @("velocity_breach","geo_anomaly","new_device")
  sla_minutes = 120
  channel     = "wire"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/api/analyse" -Method Post `
  -ContentType "application/json" `
  -Headers @{ "X-API-Key" = "fiaa-secret-key-2025" } `
  -Body $body
```

The webhook replies `{"status":"accepted"}` instantly and runs the pipeline in
the background. The **dashboard picks the result up automatically** within a few
seconds (the sidebar "Live (auto-refresh)" toggle must be on) — the new alert
appears in the Alerts queue and the finished report opens in the Investigation
tab. You can also press **"🔄 Check for new alerts"** in the sidebar to pull
immediately.

## Quick start (Docker — all 4 services)

```bash
cp .env.example .env
docker compose run app python -m rag.ingestor   # build KB into the volume
docker compose up -d                            # app + chroma + prometheus + grafana
```

| Service | URL | Notes |
|---------|-----|-------|
| Dashboard | http://localhost:8501 | Streamlit |
| Webhook | http://localhost:8001 | FastAPI |
| Metrics | http://localhost:8000/metrics | Prometheus exposition |
| Prometheus | http://localhost:9090 | scrapes `insightflow` job every 5s |
| Grafana | http://localhost:3000 | admin / **fiaa2025**, FIAA board auto-provisioned |
| ChromaDB | http://localhost:8002 | vector store |

---

## Project layout

```
fiaa/
├── app.py                  Streamlit dashboard (4 tabs)
├── ui_kit.py               theme, Indian-currency format, SVG risk gauge, CSS
├── start.py                launches webhook + metrics + dashboard together
├── core/
│   ├── llm.py              Groq client, 70b→8b→gemma2 fallback, DEMO MODE
│   └── store.py            shared SQLite store (webhook ⇄ dashboard, WAL mode)
├── configs/
│   ├── settings.py         all config from .env (Pydantic) — keys never from UI
│   └── prompts.py          the 7 agent system prompts
├── graph/
│   ├── workflow.py         LangGraph StateGraph + manual fallback + run_pipeline()
│   ├── state.py            ResearchState
│   └── ragas_eval.py       faithfulness / relevance / recall -> SQLite
├── agents/                 supervisor + incident/search/rag/reader/report/evaluator
├── rag/ingestor.py         chunk → embed → ChromaDB (keyword fallback)
├── guardrails/             input (injection/toxicity/PII) + output (hallucination/citation)
├── monitoring/             logger (structlog) · metrics (Prometheus) · tracer (LangSmith/OTel)
├── api/webhook.py          FastAPI: POST /api/analyse (key auth + rate limit + bg task)
├── data/
│   ├── knowledge_base/     playbooks, RBI guidelines, 100+ past cases
│   └── sample_alerts/      5 demo alerts (incl. the ₹4,87,000 Cayman case)
├── grafana/ prometheus.yml alert_rules.yml docker-compose.yml Dockerfile
└── requirements.txt .env.example
```

---

## Graceful degradation (why it always runs)

Every external dependency has a built-in fallback, matching the design's
stress-test scenarios:

| Missing | Fallback |
|---------|----------|
| `GROQ_API_KEY` | DEMO MODE — deterministic synthetic agent output |
| ChromaDB / sentence-transformers | keyword retriever over the same KB files |
| LangGraph | manual supervisor loop (identical routing logic) |
| Tavily | offline knowledge stub for the Search agent |
| LangSmith / OTel / RAGAS pkg | no-op tracer / lightweight heuristic RAGAS |

---

## Observability detail

- **8 Prometheus metrics**: `fiaa_agent_calls_total`, `fiaa_agent_latency_seconds`,
  `fiaa_llm_tokens_total`, `fiaa_guardrail_hits_total`, `fiaa_pipeline_latency_seconds`,
  `fiaa_last_risk_score`, `fiaa_active_runs`, `fiaa_supervisor_iterations`
  (+ `fiaa_ragas_faithfulness` for the RAGAS alert).
- **5 Grafana/Prometheus alert rules** (`alert_rules.yml`): high report latency,
  injection spike, high error rate, too many active runs, low RAGAS faithfulness.
- **structlog**: `logs/run_<id>.jsonl` per run + `logs/fiaa.jsonl` global, run_id
  auto-bound, API keys redacted.
- **LangSmith**: set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` to see the
  full chain trace per run at smith.langchain.com.

---

*Capstone Project 2025 · LangGraph · Groq · ChromaDB · Tavily · LangSmith · Docker*
