"""
rag/ingestor.py
---------------
Build, refresh and query the FIAA knowledge base.

Pipeline (per design):
  1. Ingest   fraud_playbooks.txt, rbi_guidelines.txt, past_cases.json
  2. Chunk    512-token windows, 64-token overlap
  3. Embed    all-MiniLM-L6-v2 (local, CPU, 384-dim) — no data leaves the box
  4. Store    ChromaDB PersistentClient, cosine similarity
  5. Retrieve top-5 chunks by cosine similarity


Run from the command line:  python -m rag.ingestor
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from configs.settings import settings
from monitoring.logger import get_logger

log = get_logger("rag")

KB_DIR = Path(settings.data_dir) / "knowledge_base"

try:
    import chromadb
    from chromadb.utils import embedding_functions
    _CHROMA = True
except Exception:  # pragma: no cover
    _CHROMA = False


# --------------------------------------------------------------------------
# cached singletons — built once, reused everywhere
# --------------------------------------------------------------------------
_client = None          # chromadb.PersistentClient
_embed_fn = None        # SentenceTransformer embedding function
_collection = None      # the active collection handle


def _get_client():
    global _client
    if _client is None and _CHROMA:
        Path(settings.chroma_dir).mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    return _client


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None and _CHROMA:
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=settings.embed_model)
    return _embed_fn


def _reset_handles() -> None:
    """Drop the cached collection handle so the next call reconnects fresh."""
    global _collection
    _collection = None


# --------------------------------------------------------------------------
# chunking + loading
# --------------------------------------------------------------------------
def _chunk(text: str, size: int = None, overlap: int = None) -> List[str]:
    size = size or settings.chunk_size
    overlap = overlap or settings.chunk_overlap
    words = text.split()
    if not words:
        return []
    step = max(1, size - overlap)
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step)]


def _load_documents() -> List[Dict]:
    docs: List[Dict] = []

    for fname, source in [("fraud_playbooks.txt", "playbook"),
                          ("rbi_guidelines.txt", "rbi_guideline")]:
        fp = KB_DIR / fname
        if fp.exists():
            text = fp.read_text(encoding="utf-8")
            for j, ch in enumerate(_chunk(text)):
                docs.append({"id": f"{source}-{j}", "text": ch,
                             "meta": {"source": source, "file": fname}})

    cases_fp = KB_DIR / "past_cases.json"
    if cases_fp.exists():
        for c in json.loads(cases_fp.read_text(encoding="utf-8")):
            txt = (f"Case {c['case_id']} ({c['category']}, playbook {c['playbook']}): "
                   f"{c['summary']} Outcome: {c['outcome']}. Resolution: {c['resolution']}")
            docs.append({"id": c["case_id"], "text": txt,
                         "meta": {"source": "past_case", "case_id": c["case_id"],
                                  "category": c["category"], "risk_score": c["risk_score"]}})
    return docs


# --------------------------------------------------------------------------
# build / refresh
# --------------------------------------------------------------------------
def build() -> int:
    """(Re)build the ChromaDB index from scratch. Returns number of chunks."""
    docs = _load_documents()
    if not docs:
        log.warning("rag.no_documents", dir=str(KB_DIR))
        return 0

    if not _CHROMA:
        log.warning("rag.chroma_unavailable", note="keyword fallback will be used")
        return len(docs)

    client = _get_client()
    ef = _get_embed_fn()

    # clean rebuild — drop the old collection if present
    try:
        client.delete_collection(settings.chroma_collection)
    except Exception:
        pass

    col = client.create_collection(
        name=settings.chroma_collection,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    col.add(
        ids=[d["id"] for d in docs],
        documents=[d["text"] for d in docs],
        metadatas=[d["meta"] for d in docs],
    )
    _reset_handles()  # force a fresh reconnect on the next retrieve()
    log.info("rag.indexed", chunks=len(docs), collection=settings.chroma_collection)
    return len(docs)


def refresh() -> Dict:
    """One-click rebuild used by the dashboard. Returns a status dict."""
    try:
        n = build()
        backend = "chromadb" if (_CHROMA and n and _index_count() > 0) else "keyword"
        return {"ok": True, "chunks": n, "backend": backend,
                "message": f"Indexed {n} chunks ({backend})."}
    except Exception as e:
        log.error("rag.refresh_failed", error=str(e))
        return {"ok": False, "chunks": 0, "backend": "keyword",
                "message": f"Refresh failed: {e}. Using keyword fallback."}


def _index_count() -> int:
    """How many vectors are currently stored (0 if no Chroma index)."""
    if not _CHROMA:
        return 0
    try:
        client = _get_client()
        ef = _get_embed_fn()
        col = client.get_collection(settings.chroma_collection, embedding_function=ef)
        return col.count()
    except Exception:
        return 0


def ensure_index() -> int:
    """Build the index automatically if it does not exist yet. Idempotent."""
    if not _CHROMA:
        return 0
    n = _index_count()
    if n == 0:
        log.info("rag.auto_build", reason="empty or missing collection")
        return build()
    return n


def stats() -> Dict:
    """Live knowledge-base stats for the dashboard's System tab."""
    cases = 0
    try:
        cases = len(json.loads((KB_DIR / "past_cases.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    return {
        "backend": "chromadb" if _CHROMA else "keyword (chromadb not installed)",
        "indexed_chunks": _index_count(),
        "source_documents": len(_load_documents()),
        "past_cases": cases,
        "collection": settings.chroma_collection,
        "chroma_dir": settings.chroma_dir,
    }


# --------------------------------------------------------------------------
# retrieve
# --------------------------------------------------------------------------
_kw_docs: List[Dict] = []


def _keyword_retrieve(query: str, k: int) -> List[Dict]:
    global _kw_docs
    if not _kw_docs:
        _kw_docs = _load_documents()
    q = set(re.findall(r"[a-z0-9]+", query.lower()))
    scored = []
    for d in _kw_docs:
        words = set(re.findall(r"[a-z0-9]+", d["text"].lower()))
        overlap = len(q & words)
        if overlap:
            scored.append((overlap / (len(q) + 1), d))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"text": d["text"], "meta": d["meta"], "similarity": round(s, 3)}
            for s, d in scored[:k]]


def _get_collection():
    """Return the cached collection handle, reconnecting only when needed."""
    global _collection
    if _collection is not None:
        return _collection
    client = _get_client()
    ef = _get_embed_fn()
    _collection = client.get_collection(settings.chroma_collection, embedding_function=ef)
    return _collection


def retrieve(query: str, k: int = None) -> List[Dict]:
    """Return top-k chunks: [{text, meta, similarity}]."""
    k = k or settings.rag_top_k
    if _CHROMA:
        try:
            ensure_index()                      # auto-build on first use
            col = _get_collection()
            res = col.query(query_texts=[query], n_results=k)
            out = []
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0],
                                       res["distances"][0]):
                out.append({"text": doc, "meta": meta,
                            "similarity": round(1 - dist, 3)})  # cosine dist -> sim
            if out:
                return out
        except Exception as e:  # collection missing / locked -> graceful fallback
            log.warning("rag.query_fallback", error=str(e))
            _reset_handles()
    return _keyword_retrieve(query, k)


if __name__ == "__main__":
    n = build()
    print(f"Indexed {n} chunks into ChromaDB ({settings.chroma_collection}).")
    print("Stats:", json.dumps(stats(), indent=2))
    print("\nSample query 'cross-border wire layering high value':")
    for hit in retrieve("cross-border wire layering high value")[:3]:
        print(f"  [{hit['similarity']}] {hit['meta'].get('source')} :: {hit['text'][:90]}...")
