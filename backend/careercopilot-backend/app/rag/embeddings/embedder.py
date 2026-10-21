"""
app/rag/embeddings/embedder.py
───────────────────────────────
Embedding generation using sentence-transformers.

Features:
  - Singleton model instance (loaded once per process)
  - Batch processing with configurable batch size
  - LRU cache for repeated identical texts
  - Normalised vectors (unit norm) for cosine similarity
  - Fallback to a lightweight model if primary model fails
  - Device selection: cpu / cuda / mps (Apple Silicon)
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Model catalogue — ordered by quality vs speed tradeoff
_MODEL_CATALOGUE = {
    "all-MiniLM-L6-v2":          {"dims": 384,  "max_seq": 256,  "size_mb": 90},
    "all-MiniLM-L12-v2":         {"dims": 384,  "max_seq": 256,  "size_mb": 130},
    "all-mpnet-base-v2":          {"dims": 768,  "max_seq": 514,  "size_mb": 420},
    "BAAI/bge-small-en-v1.5":    {"dims": 384,  "max_seq": 512,  "size_mb": 130},
    "BAAI/bge-base-en-v1.5":     {"dims": 768,  "max_seq": 512,  "size_mb": 430},
    "BAAI/bge-large-en-v1.5":    {"dims": 1024, "max_seq": 512,  "size_mb": 1340},
}

_FALLBACK_MODEL = "all-MiniLM-L6-v2"


# ── Singleton loader ──────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_model(model_name: str, device: str):  # type: ignore[return]
    """Load and cache the SentenceTransformer model (once per process)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
        logger.info("loading_embedding_model", model=model_name, device=device)
        model = SentenceTransformer(model_name, device=device)
        logger.info("embedding_model_loaded", model=model_name,
                    dims=model.get_sentence_embedding_dimension())
        return model
    except Exception as exc:
        logger.error("embedding_model_load_failed", model=model_name, error=str(exc))
        if model_name != _FALLBACK_MODEL:
            logger.warning("falling_back_to", model=_FALLBACK_MODEL)
            return _load_model(_FALLBACK_MODEL, device)
        raise


def get_model():
    return _load_model(settings.EMBEDDING_MODEL, settings.EMBEDDING_DEVICE)


# ── Text hash cache ───────────────────────────────────────────────────────────
_embed_cache: dict[str, list[float]] = {}
_CACHE_MAX = 5000


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


# ── Core embedding function ───────────────────────────────────────────────────
def embed_texts(
    texts:      list[str],
    batch_size: int = 64,
    normalize:  bool = True,
    show_progress: bool = False,
) -> list[list[float]]:
    """
    Embed a list of texts, returning a list of float vectors.
    Uses in-process LRU cache to avoid re-embedding identical texts.
    """
    if not texts:
        return []

    model      = get_model()
    results:   list[list[float]] = [None] * len(texts)  # type: ignore[list-item]
    uncached_indices: list[int]  = []
    uncached_texts:   list[str]  = []

    # Check cache
    for i, text in enumerate(texts):
        key = _cache_key(text)
        if key in _embed_cache:
            results[i] = _embed_cache[key]
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    # Batch-embed uncached texts
    if uncached_texts:
        all_vecs: list[list[float]] = []
        for start in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[start: start + batch_size]
            vecs  = model.encode(
                batch,
                normalize_embeddings=normalize,
                show_progress_bar=show_progress and len(batch) > 20,
                batch_size=min(batch_size, len(batch)),
            )
            all_vecs.extend(vecs.tolist())

        # Store in cache (evict oldest if full)
        for idx, vec in zip(uncached_indices, all_vecs):
            results[idx] = vec
            key = _cache_key(texts[idx])
            if len(_embed_cache) >= _CACHE_MAX:
                _embed_cache.pop(next(iter(_embed_cache)))
            _embed_cache[key] = vec

    logger.debug(
        "texts_embedded",
        total=len(texts),
        cached=len(texts) - len(uncached_texts),
        fresh=len(uncached_texts),
    )
    return results


def embed_query(text: str, normalize: bool = True) -> list[float]:
    """Embed a single query string."""
    return embed_texts([text], normalize=normalize)[0]


def get_embedding_dimension() -> int:
    """Return the dimension of the current embedding model."""
    model = get_model()
    return int(model.get_sentence_embedding_dimension())


def get_known_embedding_dims(model_name: str | None = None) -> int:
    """
    Cheap dimension lookup from the static model catalogue — does NOT load
    the model. Used by admin stats endpoints that just need an estimate
    (e.g. storage size) without paying the cost of a full model load.
    Falls back to 384 (MiniLM-class default) for unknown model names.
    """
    name = model_name or settings.EMBEDDING_MODEL
    return _MODEL_CATALOGUE.get(name, {}).get("dims", 384)


# ── LangChain Embeddings adapter ─────────────────────────────────────────────
class SentenceTransformerEmbeddings(Embeddings):
    """
    LangChain-compatible Embeddings class wrapping our SentenceTransformer.
    Drop-in replacement for OpenAIEmbeddings in any LangChain chain.
    """

    def __init__(
        self,
        model_name: str = settings.EMBEDDING_MODEL,
        device:     str = settings.EMBEDDING_DEVICE,
        batch_size: int = 64,
    ) -> None:
        self.model_name = model_name
        self.device     = device
        self.batch_size = batch_size
        # Eager-load model at construction time (avoids first-query lag)
        _load_model(model_name, device)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts, batch_size=self.batch_size)

    def embed_query(self, text: str) -> list[float]:
        return embed_query(text)

    @property
    def embedding_dimension(self) -> int:
        return get_embedding_dimension()


# ── Module-level singleton instance ──────────────────────────────────────────
@lru_cache(maxsize=1)
def get_embeddings() -> SentenceTransformerEmbeddings:
    """Return cached SentenceTransformerEmbeddings instance."""
    return SentenceTransformerEmbeddings()
