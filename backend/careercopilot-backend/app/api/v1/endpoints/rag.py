"""
app/api/v1/endpoints/rag.py
────────────────────────────
RAG pipeline REST + SSE endpoints:

  POST   /api/v1/rag/chat                     — single-turn Q&A (sync)
  POST   /api/v1/rag/chat/stream              — streaming Q&A (SSE)
  GET    /api/v1/rag/search                   — raw chunk retrieval (debug / FE search)
  GET    /api/v1/rag/categories               — list all KB categories + stats
  GET    /api/v1/rag/categories/{key}/stats   — stats for one category
  POST   /api/v1/rag/admin/ingest/{category}  — ingest built-in KB for a category  [admin]
  POST   /api/v1/rag/admin/ingest/all         — ingest all categories               [admin]
  POST   /api/v1/rag/admin/upload/{category}  — upload + ingest a document          [admin]
  DELETE /api/v1/rag/admin/collections/{cat}  — delete & re-index a collection      [admin]
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import AdminUser, CurrentUser, DBSession
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.rag.chains.rag_chain import RAGResponse, get_rag_chain, stream_rag_chain
from app.rag.kb_categories import CATEGORY_ORDER, KB_CATEGORIES, get_category
from app.rag.processors.ingestion import (
    IngestionResult,
    ingest_all_categories,
    ingest_bytes,
    ingest_category,
)
from app.rag.retriever.retriever import RetrievedChunk, retrieve_chunks
from app.rag.vectorstore.chroma_store import get_vectorstore
from app.rag.vectorstore.index_tracker import record_indexed
from app.schemas.user import APIResponse

router  = APIRouter(prefix="/rag", tags=["RAG Knowledge Base"])
logger  = get_logger(__name__)

# Shared with app/api/v1/endpoints/admin_extended.py — both routers read/write
# the same on-disk copy of uploaded KB documents so "Files on Disk", rename,
# single-document re-index, and preview all see what was actually uploaded here.
_KB_UPLOAD_DIR = Path(settings.KNOWLEDGE_BASE_DIR) / "_uploads"


# ─────────────────────────────────────────────────────────────────────────────
# Helper schemas (inline — avoids extra schema file)
# ─────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    query:        str            = Field(..., min_length=3, max_length=2000)
    categories:   list[str]     = Field(default_factory=list,
                                        description="Limit to specific KB categories. Empty = auto-detect.")
    chat_history: list[dict]    = Field(default_factory=list,
                                        description='[{"role":"user","content":"..."},...]')
    top_k:        int           = Field(5,  ge=1, le=20)
    score_threshold: float      = Field(0.30, ge=0.0, le=1.0)


class ChatResponseData(BaseModel):
    answer:      str
    citations:   list[dict]
    chunks_used: int
    categories:  list[str]
    model_used:  str
    latency_ms:  int
    tokens_used: int
    query:       str
    has_answer:  bool
    answered_from_kb: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# 1. Single-turn RAG chat (synchronous)
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/chat",
    response_model=APIResponse,
    summary="Ask a career/technical question (synchronous)",
)
def chat(
    req:          ChatRequest,
    current_user: CurrentUser,
    db:           DBSession,
) -> APIResponse:
    """
    Full RAG pipeline:
      1. Auto-route query to relevant knowledge base categories
      2. Retrieve top-k most relevant chunks via ChromaDB + MMR re-ranking
      3. Build context-aware prompt
      4. Generate answer via the configured LLM with source citations
      5. Return structured response

    **categories**: leave empty for automatic routing, or specify e.g. `["dbms","java"]`
    """
    cats = [c for c in req.categories if c in KB_CATEGORIES] or None

    result: RAGResponse = get_rag_chain(
        query=req.query,
        categories=cats,
        chat_history=req.chat_history,
        k=req.top_k,
        score_threshold=req.score_threshold,
    )

    from app.models.agent_log import AgentLogStatus, AgentName
    from app.services.agent_log_service import log_call
    log_call(
        db, user_id=current_user.user_id, agent_name=AgentName.RAG_CHAIN,
        status=AgentLogStatus.SUCCESS if result.has_answer else AgentLogStatus.FAILED,
        latency_ms=result.latency_ms, output_tokens=result.tokens_used,
        extra_metadata={
            "categories": result.categories, "chunks_used": result.chunks_used,
            "answered_from_kb": result.answered_from_kb,
        },
    )

    logger.info(
        "rag_chat",
        user_id=current_user.user_id,
        query=req.query[:60],
        chunks=result.chunks_used,
        answered_from_kb=result.answered_from_kb,
        ms=result.latency_ms,
    )

    return APIResponse(
        message="Answer generated.",
        data=ChatResponseData(
            answer=result.answer,
            citations=result.citations,
            chunks_used=result.chunks_used,
            categories=result.categories,
            model_used=result.model_used,
            latency_ms=result.latency_ms,
            tokens_used=result.tokens_used,
            query=result.query,
            has_answer=result.has_answer,
            answered_from_kb=result.answered_from_kb,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Streaming RAG chat (Server-Sent Events)
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/chat/stream",
    summary="Ask a question with streaming token response (SSE)",
    response_class=StreamingResponse,
)
async def chat_stream(
    req:          ChatRequest,
    current_user: CurrentUser,
) -> StreamingResponse:
    """
    Streams the RAG answer token-by-token using Server-Sent Events.

    **Frontend usage:**
    ```javascript
    const source = new EventSource('/api/v1/rag/chat/stream');
    source.onmessage = (e) => {
        if (e.data === '[DONE]') source.close();
        else output.textContent += e.data;
    };
    ```
    """
    cats = [c for c in req.categories if c in KB_CATEGORIES] or None

    async def event_generator() -> AsyncIterator[str]:
        try:
            for token in stream_rag_chain(
                query=req.query,
                categories=cats,
                chat_history=req.chat_history,
                k=req.top_k,
            ):
                # SSE format: "data: <payload>\n\n"
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            logger.error("rag_stream_error", error=str(exc))
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":               "no-cache",
            "X-Accel-Buffering":           "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Raw chunk search (debug / frontend autocomplete)
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/search",
    response_model=APIResponse,
    summary="Retrieve raw knowledge base chunks for a query",
)
def search_chunks(
    current_user: CurrentUser,
    q:            str        = Query(..., min_length=2, description="Search query"),
    categories:   list[str] = Query(default=[], description="Filter by categories"),
    top_k:        int        = Query(5, ge=1, le=20),
    threshold:    float      = Query(0.30, ge=0.0, le=1.0),
) -> APIResponse:
    """
    Returns raw retrieved chunks without LLM generation.
    Useful for debugging retrieval quality and building autocomplete.
    """
    cats = [c for c in categories if c in KB_CATEGORIES] or None
    chunks: list[RetrievedChunk] = retrieve_chunks(
        q, categories=cats, k=top_k, score_threshold=threshold
    )

    return APIResponse(
        data={
            "query":   q,
            "total":   len(chunks),
            "chunks": [
                {
                    "content":     c.content[:400],
                    "score":       c.score,
                    "category":    c.category,
                    "filename":    c.filename,
                    "chunk_index": c.chunk_index,
                }
                for c in chunks
            ],
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. List all KB categories
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/categories",
    response_model=APIResponse,
    summary="List all knowledge base categories with document counts",
)
def list_categories(current_user: CurrentUser) -> APIResponse:
    """Returns all 9 KB categories with ChromaDB document counts."""
    store = get_vectorstore()
    stats = {s["category"]: s for s in store.get_all_stats()}

    categories = []
    for key in CATEGORY_ORDER:
        cat  = KB_CATEGORIES[key]
        stat = stats.get(key, {"count": 0, "status": "empty"})
        categories.append({
            "key":         cat.key,
            "label":       cat.label,
            "description": cat.description,
            "icon":        cat.icon,
            "color":       cat.color,
            "chunk_count": stat.get("count", 0),
            "status":      stat.get("status", "empty"),
        })

    return APIResponse(data={"categories": categories, "total": len(categories)})


# ─────────────────────────────────────────────────────────────────────────────
# 5. Single category stats
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/categories/{category_key}/stats",
    response_model=APIResponse,
    summary="Get detailed stats for one KB category",
)
def category_stats(
    category_key: str,
    current_user: CurrentUser,
) -> APIResponse:
    if category_key not in KB_CATEGORIES:
        raise ValidationError(f"Unknown category '{category_key}'. Valid: {list(KB_CATEGORIES)}")

    store = get_vectorstore()
    stat  = store.get_collection_stats(category_key)
    cat   = KB_CATEGORIES[category_key]

    return APIResponse(data={
        **stat,
        "label":       cat.label,
        "description": cat.description,
        "icon":        cat.icon,
        "topics":      list(cat.topics[:8]),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 6. Admin: ingest built-in KB for one category
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/admin/ingest/{category_key}",
    response_model=APIResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Admin] Ingest built-in knowledge base for a category",
)
def admin_ingest_category(
    category_key: str,
    _:            AdminUser,
    replace:      bool = Query(False, description="Delete existing chunks before re-indexing"),
    strategy:     str  = Query("recursive", description="Chunking strategy: recursive | sentence_window | paragraph"),
) -> APIResponse:
    """
    Triggers the ingestion pipeline for one knowledge base category.
    Reads from `app/rag/knowledge_base/{category}/` directory.

    - **replace=true**: deletes existing collection first (full re-index)
    - **replace=false**: upserts new/changed chunks (incremental)
    """
    if category_key not in KB_CATEGORIES:
        raise ValidationError(f"Unknown category: '{category_key}'")

    result: IngestionResult = ingest_category(
        category_key, replace=replace, strategy=strategy  # type: ignore[arg-type]
    )
    if result.success:
        record_indexed(category_key)

    return APIResponse(
        message=f"Ingestion {'complete' if result.success else 'failed'} for '{category_key}'.",
        data={
            "category":        result.category,
            "files_processed": result.files_processed,
            "docs_loaded":     result.docs_loaded,
            "chunks_created":  result.chunks_created,
            "chunks_stored":   result.chunks_stored,
            "duration_ms":     result.duration_ms,
            "status":          result.status,
            "errors":          result.errors,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. Admin: ingest ALL categories
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/admin/ingest/all",
    response_model=APIResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Admin] Ingest all 9 knowledge base categories",
)
def admin_ingest_all(
    _:       AdminUser,
    replace: bool = Query(False),
) -> APIResponse:
    """
    Runs the full ingestion pipeline for all 9 KB categories.
    This may take 1–5 minutes depending on document volume.
    """
    all_results = ingest_all_categories(replace=replace)
    for cat_key, res in all_results.items():
        if res.success:
            record_indexed(cat_key)

    summary = [
        {
            "category":     k,
            "chunks_stored": v.chunks_stored,
            "status":        v.status,
            "duration_ms":   v.duration_ms,
            "errors":        v.errors,
        }
        for k, v in all_results.items()
    ]
    total_chunks = sum(v.chunks_stored for v in all_results.values())
    success_cats = sum(1 for v in all_results.values() if v.success)

    return APIResponse(
        message=f"Ingested {success_cats}/{len(all_results)} categories ({total_chunks} total chunks).",
        data={"results": summary, "total_chunks": total_chunks},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 8. Admin: upload + ingest a document
# ─────────────────────────────────────────────────────────────────────────────
@router.post(
    "/admin/upload/{category_key}",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="[Admin] Upload a PDF/DOCX/TXT file into a KB category",
)
async def admin_upload_document(
    category_key: str,
    _:            AdminUser,
    file:         UploadFile = File(..., description="PDF, DOCX, TXT, MD, or JSON file"),
    replace:      bool       = Form(False, description="Remove existing chunks from this file first"),
    strategy:     str        = Form("recursive", description="Chunking strategy"),
) -> APIResponse:
    """
    Upload a document and immediately ingest it into the specified KB category.
    Supported: .pdf, .docx, .txt, .md, .json, .jsonl
    """
    if category_key not in KB_CATEGORIES:
        raise ValidationError(f"Unknown category: '{category_key}'")

    ALLOWED_MIMES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain", "text/markdown", "application/json",
        "application/jsonlines",
    }
    mime = (file.content_type or "application/octet-stream").lower()
    # Be lenient — check extension too
    ext = (file.filename or "").split(".")[-1].lower()
    if mime not in ALLOWED_MIMES and ext not in {"pdf","docx","txt","md","json","jsonl"}:
        raise ValidationError(f"Unsupported file type: {mime}")

    data = await file.read()
    if len(data) < 10:
        raise ValidationError("Uploaded file is empty.")

    # ── Duplicate detection ──────────────────────────────────────────────────
    # Same filename already present, or identical content under a different
    # name (content hash match) — flag it in the response; the admin can
    # still proceed (e.g. `replace=true` to intentionally overwrite).
    content_hash = hashlib.sha256(data).hexdigest()
    dest_dir = _KB_UPLOAD_DIR / category_key
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = file.filename or f"upload.{ext}"
    dest_path = dest_dir / filename

    duplicate_of: str | None = None
    name_collision = dest_path.exists()
    if not name_collision:
        for existing in dest_dir.iterdir():
            if existing.is_file() and hashlib.sha256(existing.read_bytes()).hexdigest() == content_hash:
                duplicate_of = existing.name
                break

    # Persist a copy on disk so it can be previewed, renamed, or re-indexed
    # individually later without needing to re-upload.
    dest_path.write_bytes(data)

    result: IngestionResult = ingest_bytes(
        data=data,
        filename=filename,
        category=category_key,
        mime_type=mime,
        replace=replace,
        strategy=strategy,  # type: ignore[arg-type]
    )
    if result.success:
        record_indexed(category_key)

    return APIResponse(
        message=f"Document ingested into '{category_key}' ({result.chunks_stored} chunks).",
        data={
            "filename":      filename,
            "category":      category_key,
            "chunks_stored": result.chunks_stored,
            "duration_ms":   result.duration_ms,
            "status":        result.status,
            "errors":        result.errors,
            "duplicate_of":  duplicate_of,
            "name_overwritten": name_collision,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Admin: delete a collection (for re-indexing)
# ─────────────────────────────────────────────────────────────────────────────
@router.delete(
    "/admin/collections/{category_key}",
    response_model=APIResponse,
    summary="[Admin] Delete all chunks in a KB category collection",
)
def admin_delete_collection(
    category_key: str,
    _:            AdminUser,
) -> APIResponse:
    """
    Deletes the entire ChromaDB collection for a category.
    Use this before re-ingesting with `replace=false` if you want a clean slate.
    """
    if category_key not in KB_CATEGORIES:
        raise ValidationError(f"Unknown category: '{category_key}'")

    store   = get_vectorstore()
    success = store.delete_collection(category_key)

    return APIResponse(
        message=f"Collection '{category_key}' {'deleted' if success else 'could not be deleted'}.",
        data={"category": category_key, "deleted": success},
    )
