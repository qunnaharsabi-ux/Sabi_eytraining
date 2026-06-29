"""
start.py — single-command launcher for the full FIAA stack.

Runs three things in one process group:
  1. Prometheus metrics endpoint   ->  http://localhost:8000/metrics
  2. FastAPI webhook receiver       ->  http://localhost:8001/api/analyse
  3. Streamlit dashboard            ->  http://localhost:8501

Usage:
    python start.py

The Streamlit dashboard also works entirely on its own
(`streamlit run app.py`) — this launcher is only needed when you want the
FastAPI webhook live so the bank rule-engine (or curl) can POST alerts.

Ctrl-C stops everything cleanly.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# Load .env early so child processes inherit the keys.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover - dotenv optional
    pass

from configs.settings import get_settings  # noqa: E402

settings = get_settings()

PROCS: list[subprocess.Popen] = []


def _spawn(name: str, cmd: list[str]) -> None:
    print(f"  ▶ starting {name:<10} :: {' '.join(cmd)}")
    PROCS.append(subprocess.Popen(cmd, cwd=str(ROOT)))


def _shutdown(*_: object) -> None:
    print("\n⏹  shutting down FIAA services …")
    for p in PROCS:
        try:
            p.terminate()
        except Exception:
            pass
    for p in PROCS:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    sys.exit(0)


def main() -> None:
    print("=" * 66)
    print("  FIAA — Fraud Intelligence AI Assistant")
    print("  mode:", "DEMO (no Groq key)" if settings.demo_mode else "LIVE (Groq connected)")
    print("=" * 66)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 1 + 2) FastAPI webhook (it starts the Prometheus server on startup).
    _spawn(
        "webhook",
        [
            sys.executable, "-m", "uvicorn", "api.webhook:app",
            "--host", "0.0.0.0", "--port", str(settings.api_port),
        ],
    )
    time.sleep(1.0)

    # 3) Streamlit dashboard.
    _spawn(
        "dashboard",
        [
            sys.executable, "-m", "streamlit", "run", "app.py",
            "--server.port", str(settings.streamlit_port),
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
        ],
    )

    print("-" * 66)
    print(f"  Dashboard : http://localhost:{settings.streamlit_port}")
    print(f"  Webhook   : http://localhost:{settings.api_port}/api/analyse")
    print(f"  Metrics   : http://localhost:{settings.metrics_port}/metrics")
    print("-" * 66)
    print("  Press Ctrl-C to stop.\n")

    # Wait — if any child dies, bring the rest down too.
    while True:
        for p in PROCS:
            if p.poll() is not None:
                _shutdown()
        time.sleep(1.0)


if __name__ == "__main__":
    main()
