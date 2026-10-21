"""
app/rag/vectorstore/chroma_store.py
────────────────────────────────────
ChromaDB vector store with one collection per knowledge-base category.

Architecture:
  careercopilot_dbms
  careercopilot_operating_systems
  careercopilot_computer_networks
  ... etc.

Features:
  - Persistent storage (disk-backed)
  - Upsert deduplication by chunk_id
  - Collection stats and health check
  - Batch upsert with configurable size
  - Cross-collection search (searches all or selected categories)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embeddings.embedder import get_embeddings
from app.rag.kb_categories import KB_CATEGORIES, get_collection_name

logger = get_logger(__name__)


# ── ChromaDB client (singleton) ───────────────────────────────────────────────
@lru_cache(maxsize=1)
def _get_chroma_client():
    import chromadb  # type: ignore[import]
    persist_dir = Path(settings.CHROMA_PERSIST_DIR)
    persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_dir))
    logger.info("chromadb_client_init", persist_dir=str(persist_dir))
    return client


# ── Per-collection store factory ──────────────────────────────────────────────
def _get_langchain_chroma(collection_name: str) -> Chroma:
    """Return a LangChain Chroma wrapper for a specific collection."""
    return Chroma(
        client=_get_chroma_client(),
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        collection_metadata={"hnsw:space": "cosine"},
    )


# ── Main ChromaStore class ────────────────────────────────────────────────────
class ChromaStore:
    """
    Manages ChromaDB collections for all knowledge base categories.
    Use the module-level `get_vectorstore()` to get a shared instance.
    """

    def __init__(self, prefix: str = settings.CHROMA_COLLECTION_PREFIX) -> None:
        self._prefix   = prefix
        self._stores:  dict[str, Chroma] = {}

    def _store(self, category: str) -> Chroma:
        """Lazy-load and cache the Chroma instance for a category."""
        if category not in self._stores:
            cname = get_collection_name(category, self._prefix)
            self._stores[category] = _get_langchain_chroma(cname)
        return self._stores[category]

    def get_langchain_store(self, category: str) -> Chroma:
        """Public accessor — returns the underlying LangChain Chroma wrapper
        for a category, e.g. for admin endpoints that need `.get(...)` with
        raw metadatas/documents rather than a similarity search."""
        return self._store(category)

    # ── Upsert ────────────────────────────────────────────────────────────────
    def upsert(
        self,
        documents:  list[Document],
        category:   str,
        batch_size: int = 100,
    ) -> int:
        """
        Upsert documents into the category collection.
        Uses chunk_id as the ChromaDB document ID for deduplication.
        Returns count of upserted chunks.
        """
        if not documents:
            return 0

        store = self._store(category)
        total = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i: i + batch_size]
            texts    = [d.page_content for d in batch]
            metas    = [_sanitise_metadata(d.metadata) for d in batch]
            ids      = [m.get("chunk_id", f"{category}_{i+j}") for j, m in enumerate(metas)]

            store.add_texts(texts=texts, metadatas=metas, ids=ids)
            total += len(batch)
            logger.info("upserted_batch", category=category, batch=len(batch), total_so_far=total)

        logger.info("upsert_complete", category=category, total=total)
        return total

    # ── Similarity Search ─────────────────────────────────────────────────────
    def similarity_search(
        self,
        query:      str,
        category:   str,
        k:          int   = settings.RAG_TOP_K,
        score_threshold: float = settings.RAG_SCORE_THRESHOLD,
        filter_meta: dict | None = None,
    ) -> list[tuple[Document, float]]:
        """
        Search a single category collection.
        Returns list of (Document, relevance_score) sorted by score desc.
        Scores are cosine similarity [0, 1] — higher = more relevant.
        """
        store = self._store(category)
        try:
            results = store.similarity_search_with_relevance_scores(
                query,
                k=k * 2,  # over-fetch then filter
                filter=filter_meta,
            )
        except Exception as exc:
            logger.error("similarity_search_error", category=category, error=str(exc))
            return []

        # Filter by threshold and take top-k
        filtered = [(doc, score) for doc, score in results if score >= score_threshold]
        filtered.sort(key=lambda x: x[1], reverse=True)
        return filtered[:k]

    def multi_category_search(
        self,
        query:      str,
        categories: list[str] | None = None,
        k:          int              = settings.RAG_TOP_K,
        score_threshold: float       = settings.RAG_SCORE_THRESHOLD,
    ) -> list[tuple[Document, float, str]]:
        """
        Search across multiple (or all) categories.
        Returns list of (Document, score, category) sorted by score desc.
        """
        if categories is None:
            categories = list(KB_CATEGORIES.keys())

        all_results: list[tuple[Document, float, str]] = []
        for cat in categories:
            results = self.similarity_search(query, cat, k=k, score_threshold=score_threshold)
            for doc, score in results:
                all_results.append((doc, score, cat))

        # Global re-rank across categories
        all_results.sort(key=lambda x: x[1], reverse=True)
        return all_results[:k]

    # ── Collection Stats ──────────────────────────────────────────────────────
    def get_collection_stats(self, category: str) -> dict[str, Any]:
        """Return count and metadata for a collection."""
        cname  = get_collection_name(category, self._prefix)
        client = _get_chroma_client()
        try:
            col = client.get_collection(cname)
            return {
                "category":   category,
                "collection": cname,
                "count":      col.count(),
                "status":     "ready",
            }
        except Exception:
            return {"category": category, "collection": cname, "count": 0, "status": "empty"}

    def get_all_stats(self) -> list[dict[str, Any]]:
        return [self.get_collection_stats(cat) for cat in KB_CATEGORIES]

    def delete_collection(self, category: str) -> bool:
        """Delete an entire collection (used for re-indexing)."""
        cname  = get_collection_name(category, self._prefix)
        client = _get_chroma_client()
        try:
            client.delete_collection(cname)
            self._stores.pop(category, None)
            logger.info("collection_deleted", category=category, collection=cname)
            return True
        except Exception as exc:
            logger.error("collection_delete_error", category=category, error=str(exc))
            return False

    def delete_chunks_by_source(self, category: str, source: str) -> int:
        """Remove all chunks from a specific source file."""
        store   = self._store(category)
        results = store.get(where={"source": source})
        ids     = results.get("ids", [])
        if ids:
            store.delete(ids=ids)
        logger.info("chunks_deleted_by_source", category=category, source=source, count=len(ids))
        return len(ids)


# ── Metadata sanitisation ─────────────────────────────────────────────────────
def _sanitise_metadata(meta: dict) -> dict:
    """
    ChromaDB only accepts str, int, float, bool metadata values.
    Converts lists/dicts to strings, removes None values.
    """
    clean: dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        elif isinstance(v, (list, dict)):
            clean[k] = str(v)
        else:
            clean[k] = str(v)
    return clean


# ── Module-level singleton ────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_vectorstore() -> ChromaStore:
    """Return the shared ChromaStore instance."""
    return ChromaStore()
