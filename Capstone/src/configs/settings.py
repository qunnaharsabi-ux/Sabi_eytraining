"""
configs/settings.py
-------------------
Single source of truth for all configuration.

Every secret and tunable is read from the environment (.env) via Pydantic
BaseSettings. API keys are NEVER accepted from the UI — the Streamlit app
only ever reads `settings.*`, it can never set a key.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

try:
    # pydantic v2
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _V2 = True
except ImportError:  # pragma: no cover - pydantic v1 fallback
    from pydantic import BaseSettings  # type: ignore
    SettingsConfigDict = None  # type: ignore
    _V2 = False

from pydantic import Field

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """All runtime configuration. Reads from environment / .env file."""

    # ---- External API keys (read from .env ONLY) -------------------------
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    tavily_api_key: str = Field(default="", alias="TAVILY_API_KEY")
    langchain_api_key: str = Field(default="", alias="LANGCHAIN_API_KEY")

    # ---- LangSmith tracing ----------------------------------------------
    langchain_tracing_v2: bool = Field(default=False, alias="LANGCHAIN_TRACING_V2")
    langchain_project: str = Field(default="fiaa-fraud", alias="LANGCHAIN_PROJECT")
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com", alias="LANGCHAIN_ENDPOINT"
    )

    # ---- Webhook / API security -----------------------------------------
    fiaa_api_key: str = Field(default="fiaa-secret-key-2025", alias="FIAA_API_KEY")
    api_port: int = Field(default=8001, alias="API_PORT")
    metrics_port: int = Field(default=8000, alias="METRICS_PORT")
    streamlit_port: int = Field(default=8501, alias="STREAMLIT_PORT")

    # ---- Model chain (fallback on 429: 70b -> 8b -> gemma2) --------------
    model_supervisor: str = Field(default="llama-3.3-70b-versatile", alias="MODEL_SUPERVISOR")
    model_report: str = Field(default="llama-3.3-70b-versatile", alias="MODEL_REPORT")
    model_evaluator: str = Field(default="llama-3.3-70b-versatile", alias="MODEL_EVALUATOR")
    model_small: str = Field(default="llama-3.1-8b-instant", alias="MODEL_SMALL")
    model_fallback: str = Field(default="gemma2-9b-it", alias="MODEL_FALLBACK")

    # ---- RAG / embeddings -----------------------------------------------
    embed_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBED_MODEL")
    chroma_dir: str = Field(default=str(ROOT / "chroma_db"), alias="CHROMA_DIR")
    chroma_collection: str = Field(default="fiaa_knowledge", alias="CHROMA_COLLECTION")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")
    chunk_size: int = Field(default=512, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=64, alias="CHUNK_OVERLAP")

    # ---- Pipeline behaviour ---------------------------------------------
    iteration_cap: int = Field(default=5, alias="ITERATION_CAP")
    high_risk_threshold: float = Field(default=7.0, alias="HIGH_RISK_THRESHOLD")
    max_alert_chars: int = Field(default=5000, alias="MAX_ALERT_CHARS")
    env: str = Field(default="dev", alias="ENV")  # dev | prod

    # ---- Paths -----------------------------------------------------------
    logs_dir: str = Field(default=str(ROOT / "logs"), alias="LOGS_DIR")
    data_dir: str = Field(default=str(ROOT / "data"), alias="DATA_DIR")
    sqlite_path: str = Field(default=str(ROOT / "fiaa.db"), alias="SQLITE_PATH")

    if _V2:
        model_config = SettingsConfigDict(
            env_file=str(ROOT / ".env"),
            env_file_encoding="utf-8",
            populate_by_name=True,
            extra="ignore",
        )
    else:  # pragma: no cover
        class Config:
            env_file = str(ROOT / ".env")
            env_file_encoding = "utf-8"
            allow_population_by_field_name = True

    # ---- Convenience flags ----------------------------------------------
    @property
    def has_groq(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key.strip())

    @property
    def has_langsmith(self) -> bool:
        return bool(self.langchain_api_key.strip()) and self.langchain_tracing_v2

    @property
    def demo_mode(self) -> bool:
        """When no Groq key is present we run a fully-offline demo pipeline
        so the dashboard is still impressive without live credentials."""
        return not self.has_groq

    @property
    def model_chain(self) -> List[str]:
        """Ordered fallback list used by the LLM client on rate limits."""
        seen, chain = set(), []
        for m in (self.model_report, self.model_small, self.model_fallback):
            if m and m not in seen:
                seen.add(m)
                chain.append(m)
        return chain


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    Path(s.logs_dir).mkdir(parents=True, exist_ok=True)
    # Propagate LangSmith env so LangGraph/LangChain pick it up automatically
    import os
    if s.has_langsmith:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", s.langchain_api_key)
        os.environ.setdefault("LANGCHAIN_PROJECT", s.langchain_project)
        os.environ.setdefault("LANGCHAIN_ENDPOINT", s.langchain_endpoint)
    return s


settings = get_settings()
