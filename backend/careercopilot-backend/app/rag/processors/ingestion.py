"""
app/rag/processors/ingestion.py
────────────────────────────────
Document ingestion pipeline orchestrator.

Pipeline stages:
  Load → Chunk → Embed (via ChromaStore) → Store → Track

Provides:
  ingest_file()      — ingest a single file
  ingest_directory() — ingest all files in a category directory
  ingest_category()  — ingest the full built-in knowledge base for a category
  ingest_documents() — ingest pre-loaded Document objects
  ingest_bytes()     — ingest from uploaded bytes (admin upload API)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.kb_categories import KB_CATEGORIES
from app.rag.loaders.document_loader import load_bytes, load_directory, load_file
from app.rag.processors.chunker import chunk_documents
from app.rag.vectorstore.chroma_store import get_vectorstore

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    category:       str
    files_processed: int = 0
    docs_loaded:    int  = 0
    chunks_created: int  = 0
    chunks_stored:  int  = 0
    errors:         list[str] = field(default_factory=list)
    duration_ms:    int  = 0
    status:         str  = "success"  # success | partial | failed

    @property
    def success(self) -> bool:
        return self.status != "failed"


# ── Core ingestion pipeline ───────────────────────────────────────────────────
def ingest_documents(
    documents:  list[Document],
    category:   str,
    strategy:   str = "recursive",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    replace:    bool = False,
) -> IngestionResult:
    """
    Chunk pre-loaded documents and upsert into ChromaDB.

    Args:
        documents:  List of loaded LangChain Documents
        category:   KB category key (e.g. 'dbms', 'python')
        strategy:   Chunking strategy: recursive | sentence_window | paragraph
        chunk_size: Override default chunk size
        chunk_overlap: Override default overlap
        replace:    If True, delete existing chunks for the same sources first
    """
    t0     = time.monotonic()
    result = IngestionResult(category=category, docs_loaded=len(documents))

    if not documents:
        result.status = "failed"
        result.errors.append("No documents provided")
        return result

    store = get_vectorstore()

    # Optional: delete old chunks from same sources
    if replace:
        sources = {d.metadata.get("source", "") for d in documents}
        for src in sources:
            if src:
                store.delete_chunks_by_source(category, src)

    # Chunk
    try:
        cat_cfg    = KB_CATEGORIES.get(category)
        eff_size   = chunk_size   or (cat_cfg.chunk_size   if cat_cfg else settings.CHUNK_SIZE)
        eff_overlap = chunk_overlap or (cat_cfg.chunk_overlap if cat_cfg else settings.CHUNK_OVERLAP)

        chunks = chunk_documents(
            documents,
            strategy=strategy,      # type: ignore[arg-type]
            chunk_size=eff_size,
            chunk_overlap=eff_overlap,
        )
        result.chunks_created = len(chunks)
    except Exception as exc:
        result.status = "failed"
        result.errors.append(f"Chunking error: {exc}")
        logger.error("ingestion_chunking_error", category=category, error=str(exc))
        return result

    # Upsert into ChromaDB
    try:
        stored = store.upsert(chunks, category)
        result.chunks_stored = stored
    except Exception as exc:
        result.status  = "partial" if result.chunks_created > 0 else "failed"
        result.errors.append(f"Storage error: {exc}")
        logger.error("ingestion_storage_error", category=category, error=str(exc))

    result.duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "ingestion_complete",
        category=category,
        docs=result.docs_loaded,
        chunks=result.chunks_stored,
        ms=result.duration_ms,
    )
    return result


# ── File-level ingestion ──────────────────────────────────────────────────────
def ingest_file(
    path:     str | Path,
    category: str,
    **kwargs,
) -> IngestionResult:
    """Ingest a single file."""
    docs = load_file(path, category)
    result = ingest_documents(docs, category, **kwargs)
    result.files_processed = 1
    return result


# ── Directory-level ingestion ─────────────────────────────────────────────────
def ingest_directory(
    directory: str | Path,
    category:  str,
    **kwargs,
) -> IngestionResult:
    """Ingest all supported files in a directory."""
    all_docs: list[Document] = list(load_directory(directory, category))
    result = ingest_documents(all_docs, category, **kwargs)

    # Count unique files
    sources = {d.metadata.get("source", "") for d in all_docs}
    result.files_processed = len(sources)
    return result


# ── Category-level ingestion (built-in knowledge base) ───────────────────────
def ingest_category(
    category:  str,
    kb_dir:    str | None = None,
    replace:   bool = False,
    **kwargs,
) -> IngestionResult:
    """
    Ingest the built-in knowledge base for a specific category.
    Looks in: {KNOWLEDGE_BASE_DIR}/{category}/
    """
    kb_root = Path(kb_dir or settings.KNOWLEDGE_BASE_DIR)
    cat_dir = kb_root / category

    if not cat_dir.exists():
        logger.warning("kb_category_dir_not_found", path=str(cat_dir))
        return IngestionResult(
            category=category,
            status="failed",
            errors=[f"Directory not found: {cat_dir}"],
        )

    return ingest_directory(cat_dir, category, replace=replace, **kwargs)


# ── Bytes-level ingestion (for admin file upload API) ─────────────────────────
def ingest_bytes(
    data:      bytes,
    filename:  str,
    category:  str,
    mime_type: str = "application/pdf",
    **kwargs,
) -> IngestionResult:
    """Ingest from in-memory bytes (admin upload endpoint)."""
    docs = load_bytes(data, filename, category, mime_type)
    result = ingest_documents(docs, category, **kwargs)
    result.files_processed = 1
    return result


# ── Bulk ingestion (all categories) ──────────────────────────────────────────
def ingest_all_categories(
    kb_dir:  str | None = None,
    replace: bool       = False,
) -> dict[str, IngestionResult]:
    """
    Ingest all 9 knowledge base categories from the default KB directory.
    Returns a dict mapping category_key → IngestionResult.
    """
    results: dict[str, IngestionResult] = {}
    for cat_key in KB_CATEGORIES:
        logger.info("ingesting_category", category=cat_key)
        results[cat_key] = ingest_category(cat_key, kb_dir=kb_dir, replace=replace)
    return results
