# Playbook 3 — Debugging Production Issues (Logs & Diagnostics)

**Purpose:** Diagnose and resolve issues in the deployed FIAA stack using Docker and application logs.
**Audience:** Analyst.
**Where logs live:** Application logs are structured JSON at `/app/logs/fiaa.jsonl` inside the `app` container; the web-server/container logs are via `docker compose logs`.

---

## Step 0 — Triage: is the service healthy?

```
docker compose ps                                  # all services Up?
Invoke-RestMethod -Uri "http://<VM_IP>:8001/health"  # returns status ok?
```
- A service shows `Exited`/`Restarting` → go to "Container won't start".
- Health fails but container is Up → go to "App errors".

## Step 1 — Read the container logs (fastest first look)

```
docker compose logs -f app            # live tail
docker compose logs --tail=100 app    # last 100 lines
```
Filter (PowerShell uses `Select-String`, not `grep`):
```
docker compose logs app | Select-String "ERROR|Traceback|Exception"
docker compose logs app | Select-String "401|400|422|429"
```

## Step 2 — Read the structured application log (per-run detail)

Inside the container, `fiaa.jsonl` has one JSON line per event, tagged with `run_id`:
```
docker compose exec app tail -f /app/logs/fiaa.jsonl
```
Filter by category (grep runs INSIDE the container here):
```
docker compose exec app sh -c "grep -iE 'error' /app/logs/fiaa.jsonl | tail -20"
docker compose exec app sh -c "grep -iE 'injection_blocked|pii_redacted|toxic' /app/logs/fiaa.jsonl | tail"
docker compose exec app sh -c "grep -iE 'auth_failed|rate_limited|payload_too_large' /app/logs/fiaa.jsonl | tail"
```
Trace one investigation end-to-end by its run_id:
```
docker compose exec app sh -c "cat /app/logs/run_<run_id>.jsonl"
```

## Log severity — how to read it

| Level | Meaning | Example |
|---|---|---|
| `info` | Normal operation | `agent.success`, `pipeline.complete` |
| `warning` | Handled/flagged event | `guardrail.injection_blocked`, `api.rate_limited`, `api.auth_failed` |
| `error` | Genuine failure / unhandled exception | `webhook.pipeline_failed` |


## Common issues → cause → fix

| Symptom | Likely cause | Fix |
|---|---|---|
| Container keeps restarting | Code error on startup / missing dep | `docker compose logs app` → read the traceback; fix and rebuild |

| `Errno 10048` / port in use | Port already bound (stray process/second stack) | `docker compose down`; kill stray process; restart |

| Dashboard loads but no data | No alerts fired yet, or metric prefix mismatch | Fire alerts; use Grafana **Explore** with `fiaa_*` queries |

| 401 on every request | Wrong/missing `X-API-Key` | Check the header; check `FIAA_API_KEY` in `.env` |

| 429 responses | Rate limit hit (60/min/client) | Expected under load; slow the caller or raise the limit |

| Report looks generic / low faithfulness | Live LLM asserting beyond evidence, or KB stale | Refresh the knowledge base; check RAGAS trend |


| Grafana empty | Prometheus target down or panel metric names wrong | Check `:9090/targets`; query `fiaa_*` in Explore |

## Container won't start — deeper checks

```
docker compose logs app                 # read the exact error
docker compose exec app python -c "import app"   # (if it starts) import check
docker compose config                    # validate compose file
```

## Capture evidence for a bug report

```
docker compose logs app > app_console.log
docker compose exec app sh -c "tail -n 200 /app/logs/fiaa.jsonl" > app_events.jsonl
```

## Escalation checklist

1. Is it code (traceback in logs) or infra (VM/network/ports)?
2. Does it reproduce locally with `docker compose up`?
3. Note the `run_id` of a failing request — it links every log line for that case.
4. Roll back to the last known-good image (see Playbook 2 → Rollback) if production is down.
