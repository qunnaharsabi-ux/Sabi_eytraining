# =============================================================================
# FIAA app image — runs the Streamlit dashboard + FastAPI webhook + metrics.
# =============================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: build tools for some wheels, curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer caching).
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# App source.
COPY . .

# Build the RAG knowledge base into the image's chroma volume mount point.
# (Safe to run at build: falls back to keyword index if models unavailable.)
RUN python -m rag.ingestor || echo "RAG ingest deferred to runtime"

EXPOSE 8501 8001 8000

# start.py launches webhook (+metrics) and the Streamlit dashboard together.
CMD ["python", "start.py"]
