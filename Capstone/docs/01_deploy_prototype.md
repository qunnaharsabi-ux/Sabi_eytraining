# Playbook 1 — Deploying the FIAA Prototype (Local)

**Purpose:** Run the full FIAA stack on a local machine for development.
**Audience:** Developers / evaluators.
**Time:** ~10 minutes (first Docker build is longer).

---

## Prerequisites

- Python 3.11+ (for the non-Docker option) OR Docker Desktop (for the Docker option).


## Option A — Run locally with Python (fastest for development)

1. Open a terminal in the project root (`fiaa/`).
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate        # Windows
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create the environment file:
   ```
   .env       # then edit .env to add keys for ex groq api key, tavily api key..etc
   ```
5. Start the full stack (dashboard + webhook):
   ```
   python start.py
   ```
6. Open:
   - Dashboard: http://localhost:8501
   - Webhook health: http://localhost:8001/health

## Option B — Run with Docker Compose (matches production)

1. In the project root, ensure `.env` exists.
2. Build and start:
   ```
   docker compose up -d --build
   ```
3. Verify all services are up:
   ```
   docker compose ps
   ```
4. Open the dashboard at http://localhost:8501.

## Smoke test (confirm it works)

1. Health check returns `status: ok`:
   ```
   Invoke-RestMethod -Uri "http://localhost:8001/health"
   ```
2. Fire a test alert:
   ```
   $body = @{ alert_id="SMOKE-1"; amount=487000; destination="Singapore"; signals=@("velocity_breach") } | ConvertTo-Json
   Invoke-RestMethod -Uri "http://localhost:8001/api/analyse" -Method Post -ContentType "application/json" -Headers @{ "X-API-Key"="fiaa-secret-key-2025" } -Body $body
   ```
   Expected: `status: accepted`. The alert then appears on the dashboard.
 |

## Stop the stack

- Local: `Ctrl + C` in the `start.py` terminal.
- Docker: `docker compose down`.
