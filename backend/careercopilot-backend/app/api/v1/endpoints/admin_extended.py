"""
app/api/v1/endpoints/admin_extended.py
─────────────────────────────────────────
Additive Admin Panel endpoints — mounted alongside the existing admin.py router.

This file does NOT modify admin.py. It is registered as a second router under
the same /admin prefix in router.py, adding:

  Role Management:
    PATCH /admin/users/{id}/promote        — grant admin role
    PATCH /admin/users/{id}/demote         — strip admin role
    POST  /admin/users/{id}/reset-password — force password reset
    DELETE /admin/users/{id}                — hard delete user
    GET   /admin/users/{id}/activity       — recent agent logs for user

  Knowledge Base Management:
    POST   /admin/kb/upload/{category}     — upload PDF/DOCX/TXT/MD
    POST   /admin/kb/reindex/{category}    — rebuild embeddings for category
    DELETE /admin/kb/documents/{category}/{filename} — delete a document
    GET    /admin/kb/documents/{category}  — list documents in category

  ChromaDB Management:
    GET    /admin/chroma/collections       — list all collections with stats
    POST   /admin/chroma/collections/{cat}/reindex — rebuild one collection
    DELETE /admin/chroma/collections/{cat} — delete a collection entirely

  System Health:
    GET /admin/health/full                 — DB, Redis, ChromaDB, Groq, disk

  System Settings:
    GET  /admin/settings                   — current runtime config (safe fields only)
    PATCH /admin/settings                  — update runtime-configurable settings

  Logs:
    GET /admin/logs                        — paginated, filterable system logs
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import desc, select

from app.api.dependencies import AdminUser, DBSession
from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.user import User
from app.rag.embeddings.embedder import get_known_embedding_dims
from app.rag.kb_categories import KB_CATEGORIES
from app.rag.vectorstore.chroma_store import get_vectorstore
from app.rag.vectorstore.index_tracker import get_all_last_indexed, get_last_indexed, record_indexed
from app.schemas.user import APIResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/admin", tags=["Admin Panel — Extended"])
logger = get_logger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# ROLE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.patch("/users/{user_id}/promote", response_model=APIResponse,
              summary="[Admin] Promote a user to admin role")
def promote_user(user_id: int, admin: AdminUser, db: DBSession) -> APIResponse:
    svc  = UserService(db)
    user = svc.promote_to_admin(user_id, admin.user_id)
    db.commit()
    return APIResponse(
        message=f"{user.email} promoted to admin.",
        data={"user_id": user.user_id, "role": user.role.value},
    )


@router.patch("/users/{user_id}/demote", response_model=APIResponse,
              summary="[Admin] Demote an admin to regular user")
def demote_user(user_id: int, admin: AdminUser, db: DBSession) -> APIResponse:
    svc  = UserService(db)
    user = svc.demote_to_user(user_id, admin.user_id)
    db.commit()
    return APIResponse(
        message=f"{user.email} demoted to user.",
        data={"user_id": user.user_id, "role": user.role.value},
    )


class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password", response_model=APIResponse,
             summary="[Admin] Force-reset a user's password")
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    admin:   AdminUser,
    db:      DBSession,
) -> APIResponse:
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
    svc = UserService(db)
    svc.reset_password(user_id, payload.new_password, admin.user_id)
    db.commit()
    return APIResponse(message="Password reset successfully.")


@router.delete("/users/{user_id}", response_model=APIResponse,
               summary="[Admin] Permanently delete a user account")
def delete_user(user_id: int, admin: AdminUser, db: DBSession) -> APIResponse:
    svc = UserService(db)
    svc.delete_user(user_id, admin.user_id)
    db.commit()
    return APIResponse(message="User deleted permanently.")


@router.get("/users/{user_id}/activity", response_model=APIResponse,
            summary="[Admin] Recent agent activity for a user")
def get_user_activity(
    user_id: int,
    admin:   AdminUser,
    db:      DBSession,
    limit:   int = Query(20, ge=1, le=100),
) -> APIResponse:
    svc = UserService(db)
    activity = svc.get_activity(user_id, limit=limit)
    return APIResponse(data={"activity": activity, "total": len(activity)})


# ═════════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASE MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

_ALLOWED_KB_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
_KB_UPLOAD_DIR = Path(settings.KNOWLEDGE_BASE_DIR) / "_uploads"


@router.post("/kb/upload/{category}", response_model=APIResponse,
             summary="[Admin] Upload a document to a KB category")
async def upload_kb_document(
    category: str,
    admin:    AdminUser,
    file:     UploadFile = File(...),
) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_KB_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(_ALLOWED_KB_EXTENSIONS)}",
        )

    dest_dir = _KB_UPLOAD_DIR / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / file.filename

    content = await file.read()
    dest_path.write_bytes(content)

    logger.info("kb_document_uploaded", category=category, filename=file.filename,
                size_bytes=len(content), by_admin=admin.user_id)

    return APIResponse(
        message=f"Uploaded '{file.filename}' to category '{category}'. Run reindex to make it searchable.",
        data={
            "category": category,
            "filename": file.filename,
            "size_bytes": len(content),
            "path": str(dest_path),
        },
    )


@router.get("/kb/documents/{category}", response_model=APIResponse,
            summary="[Admin] List uploaded documents in a category")
def list_kb_documents(category: str, admin: AdminUser) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    dest_dir = _KB_UPLOAD_DIR / category
    if not dest_dir.exists():
        return APIResponse(data={"category": category, "documents": []})

    docs = []
    for f in dest_dir.iterdir():
        if f.is_file():
            stat = f.stat()
            docs.append({
                "filename":     f.name,
                "size_bytes":   stat.st_size,
                "uploaded_at":  datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "extension":    f.suffix,
            })
    return APIResponse(data={"category": category, "documents": docs, "total": len(docs)})


@router.delete("/kb/documents/{category}/{filename}", response_model=APIResponse,
              summary="[Admin] Delete an uploaded KB document and remove its ChromaDB embeddings")
def delete_kb_document(category: str, filename: str, admin: AdminUser) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    file_path = _KB_UPLOAD_DIR / category / filename
    if not file_path.exists():
        raise NotFoundError("Document", filename)

    # 1. Delete file from disk
    file_path.unlink()

    # 2. Remove ChromaDB chunks whose source matches this filename
    chunks_removed = 0
    try:
        vs = get_vectorstore()
        for source_key in [filename, file_path.stem, str(file_path)]:
            try:
                removed = vs.delete_chunks_by_source(category, source_key)
                chunks_removed += removed or 0
                if removed:
                    break
            except Exception:
                continue
    except Exception as exc:
        logger.warning("kb_chroma_delete_failed", filename=filename, error=str(exc))

    logger.info("kb_document_deleted", category=category, filename=filename,
                chunks_removed=chunks_removed, by_admin=admin.user_id)
    return APIResponse(
        message=f"Deleted '{filename}' and removed {chunks_removed} embedding chunk(s).",
        data={"filename": filename, "category": category, "chunks_removed": chunks_removed},
    )


class RenameDocumentRequest(BaseModel):
    new_filename: str


@router.patch("/kb/documents/{category}/{filename}/rename", response_model=APIResponse,
              summary="[Admin] Rename an uploaded KB document and re-index it under the new name")
def rename_kb_document(
    category: str, filename: str, payload: RenameDocumentRequest, admin: AdminUser,
) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    old_path = _KB_UPLOAD_DIR / category / filename
    if not old_path.exists():
        raise NotFoundError("Document", filename)

    new_name = Path(payload.new_filename).name  # strip any path components
    if not new_name or Path(new_name).suffix.lower() not in _ALLOWED_KB_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Invalid new filename or unsupported extension.")

    new_path = old_path.parent / new_name
    if new_path.exists():
        raise ConflictError(f"A document named '{new_name}' already exists in this category.")

    old_path.rename(new_path)

    # Re-index under the new name: drop chunks tagged with the old source,
    # re-ingest the (now-renamed) file so its chunks carry the new source name.
    chunks_removed = 0
    chunks_stored = 0
    try:
        vs = get_vectorstore()
        for source_key in [filename, old_path.stem]:
            chunks_removed += vs.delete_chunks_by_source(category, source_key) or 0

        from app.rag.processors.ingestion import ingest_file
        result = ingest_file(new_path, category, replace=False)
        chunks_stored = result.chunks_stored
        if result.success:
            record_indexed(category)
    except Exception as exc:
        logger.warning("kb_rename_reindex_failed", filename=filename, error=str(exc))

    logger.info("kb_document_renamed", category=category, old_name=filename,
                new_name=new_name, by_admin=admin.user_id)
    return APIResponse(
        message=f"Renamed '{filename}' to '{new_name}' and re-indexed ({chunks_stored} chunks).",
        data={
            "category": category, "old_filename": filename, "new_filename": new_name,
            "chunks_removed": chunks_removed, "chunks_stored": chunks_stored,
        },
    )


@router.post("/kb/documents/{category}/{filename}/reindex", response_model=APIResponse,
             summary="[Admin] Re-index a single document without touching the rest of the category")
def reindex_kb_document(category: str, filename: str, admin: AdminUser) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    file_path = _KB_UPLOAD_DIR / category / filename
    if not file_path.exists():
        raise NotFoundError("Document", filename)

    t0 = time.monotonic()
    try:
        from app.rag.processors.ingestion import ingest_file
        # replace=True drops any existing chunks for this source before re-adding,
        # so re-running this endpoint is always safe / idempotent.
        result = ingest_file(file_path, category, replace=True)
    except Exception as exc:
        logger.error("kb_single_reindex_error", filename=filename, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Re-index failed: {exc}")

    if result.success:
        record_indexed(category)

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("kb_document_reindexed", category=category, filename=filename,
                chunks=result.chunks_stored, ms=elapsed_ms, by_admin=admin.user_id)
    return APIResponse(
        message=f"Re-indexed '{filename}' ({result.chunks_stored} chunks).",
        data={
            "category": category, "filename": filename,
            "chunks_stored": result.chunks_stored, "status": result.status,
            "elapsed_ms": elapsed_ms, "errors": result.errors,
        },
    )


@router.get("/kb/documents/{category}/{filename}/preview", response_model=APIResponse,
            summary="[Admin] Extract and preview a document's text content")
def preview_kb_document(category: str, filename: str, admin: AdminUser,
                         max_chars: int = Query(3000, ge=200, le=20000)) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    file_path = _KB_UPLOAD_DIR / category / filename
    if not file_path.exists():
        raise NotFoundError("Document", filename)

    try:
        from app.rag.loaders.document_loader import load_file
        docs = load_file(file_path, category)
        full_text = "\n\n".join(d.page_content for d in docs)
    except Exception as exc:
        logger.warning("kb_preview_extract_failed", filename=filename, error=str(exc))
        raise HTTPException(status_code=422, detail=f"Could not extract text from this file: {exc}")

    truncated = len(full_text) > max_chars
    return APIResponse(data={
        "category": category, "filename": filename,
        "text": full_text[:max_chars], "truncated": truncated,
        "total_chars": len(full_text),
    })


@router.get("/kb/documents/{category}/check-duplicate", response_model=APIResponse,
            summary="[Admin] Check whether a filename or content hash already exists in a category")
def check_kb_duplicate(category: str, admin: AdminUser,
                        filename: str = Query(...)) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    dest_dir = _KB_UPLOAD_DIR / category
    exists = (dest_dir / filename).exists() if dest_dir.exists() else False
    return APIResponse(data={"category": category, "filename": filename, "name_exists": exists})


@router.get("/kb/chromadocs/{category}", response_model=APIResponse,
           summary="[Admin] List documents indexed in ChromaDB for a category")
def list_chromadocs(category: str, admin: AdminUser) -> APIResponse:
    """
    Returns unique source documents currently in ChromaDB with chunk counts.
    Reflects what is actually searchable — not just what is on disk.
    """
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    try:
        vs    = get_vectorstore()
        store = vs.get_langchain_store(category)
        result = store.get(include=["metadatas", "documents"])
        metadatas = result.get("metadatas") or []
        contents  = result.get("documents") or []
    except Exception as exc:
        logger.error("list_chromadocs_error", category=category, error=str(exc))
        return APIResponse(data={"category": category, "documents": [], "total_chunks": 0})

    source_counts: dict[str, int] = {}
    source_chars:  dict[str, int] = {}
    for meta, content in zip(metadatas, contents):
        if not meta:
            continue
        source = meta.get("source") or meta.get("filename") or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1
        source_chars[source]  = source_chars.get(source, 0) + len(content or "")

    documents = [
        {
            "source": src,
            "chunks": count,
            "avg_chunk_chars": round(source_chars.get(src, 0) / count) if count else 0,
        }
        for src, count in sorted(source_counts.items())
    ]
    total_chunks = sum(d["chunks"] for d in documents)
    total_chars  = sum(source_chars.values())
    return APIResponse(data={
        "category":         category,
        "documents":        documents,
        "total_docs":       len(documents),
        "total_chunks":     total_chunks,
        "avg_chunk_chars":  round(total_chars / total_chunks) if total_chunks else 0,
    })


@router.post("/kb/reindex/{category}", response_model=APIResponse,
            summary="[Admin] Re-index a KB category (rebuild embeddings)")
def reindex_kb_category(category: str, admin: AdminUser) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    t0 = time.monotonic()
    try:
        from app.rag.processors.ingestion import ingest_category
        result = ingest_category(category)
        chunks_indexed = result.chunks_stored
        if result.success:
            record_indexed(category)
    except Exception as exc:
        logger.error("kb_reindex_error", category=category, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}")

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    logger.info("kb_category_reindexed", category=category,
                chunks=chunks_indexed, ms=elapsed_ms, by_admin=admin.user_id)

    return APIResponse(
        message=f"Re-indexed category '{category}'.",
        data={"category": category, "chunks_indexed": chunks_indexed, "elapsed_ms": elapsed_ms},
    )


# ═════════════════════════════════════════════════════════════════════════════
# CHROMADB COLLECTION MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/chroma/collections", response_model=APIResponse,
           summary="[Admin] List all ChromaDB collections with stats")
def list_chroma_collections(admin: AdminUser) -> APIResponse:
    try:
        vs    = get_vectorstore()
        stats = vs.get_all_stats()
    except Exception as exc:
        logger.error("chroma_collections_error", error=str(exc))
        return APIResponse(data={"collections": [], "error": str(exc)})

    dims = get_known_embedding_dims(settings.EMBEDDING_MODEL)
    last_indexed_map = get_all_last_indexed()

    enriched = []
    for s in stats:
        cat_key = s["category"]
        cat_meta = KB_CATEGORIES.get(cat_key)
        count = s.get("count", 0)
        status_ = s.get("status", "unknown")

        # Health: green when the collection is reachable and has vectors,
        # yellow when reachable but empty, red when the collection errored.
        health = "green" if status_ == "ready" and count > 0 else \
                 "yellow" if status_ in ("ready", "empty") else "red"

        # Estimated storage: float32 vectors (4 bytes) × dims, per chunk —
        # ChromaDB doesn't expose a clean per-collection disk size (all
        # collections share one SQLite file), so this is a labelled estimate,
        # not a measured value.
        estimated_storage_bytes = count * dims * 4

        enriched.append({
            "category":         cat_key,
            "collection":       s.get("collection", cat_key),
            "label":            cat_meta.label if cat_meta else cat_key,
            "count":            count,
            "status":           status_,
            "health":           health,
            "embedding_model":  settings.EMBEDDING_MODEL,
            "embedding_dims":   dims,
            "estimated_storage_bytes": estimated_storage_bytes,
            "last_indexed_at":  last_indexed_map.get(cat_key),
        })

    total_storage = sum(c["estimated_storage_bytes"] for c in enriched)
    actual_sqlite_bytes = None
    try:
        sqlite_path = Path(settings.CHROMA_PERSIST_DIR) / "chroma.sqlite3"
        if sqlite_path.exists():
            actual_sqlite_bytes = sqlite_path.stat().st_size
    except Exception:
        pass

    return APIResponse(data={
        "collections": enriched,
        "total_collections": len(enriched),
        "storage_dir": settings.CHROMA_PERSIST_DIR,
        "estimated_total_storage_bytes": total_storage,
        "actual_sqlite_bytes": actual_sqlite_bytes,
    })


@router.post("/chroma/collections/{category}/reindex", response_model=APIResponse,
            summary="[Admin] Rebuild a single ChromaDB collection from scratch")
def reindex_chroma_collection(category: str, admin: AdminUser) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    try:
        vs = get_vectorstore()
        vs.delete_collection(category)
    except Exception as exc:
        logger.warning("chroma_delete_before_reindex_failed", category=category, error=str(exc))

    return reindex_kb_category(category, admin)


@router.delete("/chroma/collections/{category}", response_model=APIResponse,
              summary="[Admin] Delete a ChromaDB collection entirely")
def delete_chroma_collection(category: str, admin: AdminUser) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    try:
        vs = get_vectorstore()
        vs.delete_collection(category)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete collection: {exc}")

    logger.info("chroma_collection_deleted", category=category, by_admin=admin.user_id)
    return APIResponse(message=f"Collection '{category}' deleted.")


@router.get("/chroma/collections/{category}/chunks", response_model=APIResponse,
           summary="[Admin] View raw chunks stored in a collection (paginated)")
def view_chroma_chunks(
    category: str, admin: AdminUser,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
) -> APIResponse:
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    try:
        vs = get_vectorstore()
        store = vs.get_langchain_store(category)
        result = store.get(include=["metadatas", "documents"])
        ids       = result.get("ids") or []
        metadatas = result.get("metadatas") or []
        contents  = result.get("documents") or []
    except Exception as exc:
        logger.error("view_chroma_chunks_error", category=category, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Could not read chunks: {exc}")

    total = len(ids)
    start = (page - 1) * page_size
    end   = start + page_size
    page_rows = [
        {
            "chunk_id": cid,
            "source":   (meta or {}).get("source") or (meta or {}).get("filename") or "unknown",
            "text_preview": (content or "")[:280],
            "chunk_index": (meta or {}).get("chunk_index"),
        }
        for cid, meta, content in zip(ids[start:end], metadatas[start:end], contents[start:end])
    ]

    return APIResponse(data={
        "category": category, "chunks": page_rows,
        "total": total, "page": page, "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    })


@router.post("/chroma/collections/{category}/delete-orphans", response_model=APIResponse,
            summary="[Admin] Delete embeddings whose source file no longer exists on disk")
def delete_orphan_embeddings(category: str, admin: AdminUser) -> APIResponse:
    """
    An "orphan" chunk is one whose `source` file isn't in the uploaded-docs
    directory *or* the built-in knowledge-base directory for this category —
    i.e. the file it was created from was deleted (or renamed some other
    way) without cleaning up its embeddings.
    """
    if category not in KB_CATEGORIES:
        raise NotFoundError("KB Category", category)

    known_files: set[str] = set()
    for base in (_KB_UPLOAD_DIR / category, Path(settings.KNOWLEDGE_BASE_DIR) / category):
        if base.exists():
            known_files.update(f.name for f in base.iterdir() if f.is_file())
            known_files.update(f.stem for f in base.iterdir() if f.is_file())

    try:
        vs = get_vectorstore()
        store = vs.get_langchain_store(category)
        result = store.get(include=["metadatas"])
        ids       = result.get("ids") or []
        metadatas = result.get("metadatas") or []
    except Exception as exc:
        logger.error("delete_orphans_read_error", category=category, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Could not read collection: {exc}")

    orphan_ids = [
        cid for cid, meta in zip(ids, metadatas)
        if (meta or {}).get("source") and (meta or {}).get("source") not in known_files
        and Path((meta or {}).get("source", "")).stem not in known_files
    ]

    if orphan_ids:
        store.delete(ids=orphan_ids)

    logger.info("orphan_embeddings_deleted", category=category,
                count=len(orphan_ids), by_admin=admin.user_id)
    return APIResponse(
        message=f"Removed {len(orphan_ids)} orphaned chunk(s) from '{category}'.",
        data={"category": category, "orphans_removed": len(orphan_ids)},
    )


# ═════════════════════════════════════════════════════════════════════════════
# SYSTEM HEALTH MONITORING
# ═════════════════════════════════════════════════════════════════════════════

def _check_database(db: DBSession) -> dict:
    try:
        db.execute(select(1))
        return {"status": "green", "message": "Connected"}
    except Exception as exc:
        return {"status": "red", "message": str(exc)[:200]}


def _check_redis() -> dict:
    try:
        from app.db.redis import get_redis_client
        client = get_redis_client()
        client.ping()
        return {"status": "green", "message": "Connected"}
    except Exception as exc:
        return {"status": "red", "message": str(exc)[:200]}


def _check_chromadb() -> dict:
    try:
        vs = get_vectorstore()
        vs.get_all_stats()
        return {"status": "green", "message": "Connected"}
    except Exception as exc:
        return {"status": "yellow", "message": str(exc)[:200]}


def _check_groq() -> dict:
    if not settings.GROQ_API_KEY:
        return {"status": "yellow", "message": "GROQ_API_KEY not configured"}
    return {"status": "green", "message": f"Configured ({settings.GROQ_MODEL})"}


def _check_disk() -> dict:
    try:
        total, used, free = shutil.disk_usage(".")
        pct_used = round((used / total) * 100, 1)
        status_label = "green" if pct_used < 80 else "yellow" if pct_used < 95 else "red"
        return {
            "status": status_label,
            "message": f"{pct_used}% used",
            "free_gb": round(free / (1024**3), 2),
            "total_gb": round(total / (1024**3), 2),
        }
    except Exception as exc:
        return {"status": "yellow", "message": str(exc)[:200]}


@router.get("/health/full", response_model=APIResponse,
           summary="[Admin] Full system health check")
def full_health_check(admin: AdminUser, db: DBSession) -> APIResponse:
    checks = {
        "database":         _check_database(db),
        "redis":             _check_redis(),
        "chromadb":          _check_chromadb(),
        "groq_api":          _check_groq(),
        "disk":              _check_disk(),
    }
    statuses = [c["status"] for c in checks.values()]
    overall  = "red" if "red" in statuses else "yellow" if "yellow" in statuses else "green"

    return APIResponse(data={"overall_status": overall, "checks": checks})


# ═════════════════════════════════════════════════════════════════════════════
# SYSTEM SETTINGS (runtime-configurable, safe fields only)
# ═════════════════════════════════════════════════════════════════════════════

class SettingsUpdateRequest(BaseModel):
    rag_top_k:            Optional[int]   = None
    rag_score_threshold:  Optional[float] = None
    chunk_size:           Optional[int]   = None
    chunk_overlap:        Optional[int]   = None
    rate_limit_per_minute: Optional[int]  = None
    max_resume_size_mb:   Optional[int]   = None


@router.get("/settings", response_model=APIResponse,
           summary="[Admin] Get current runtime configuration")
def get_settings_view(admin: AdminUser) -> APIResponse:
    """Returns only safe, non-secret configuration values."""
    return APIResponse(data={
        "llm": {
            "default_provider": settings.DEFAULT_LLM_PROVIDER,
            "default_model":    settings.DEFAULT_LLM_MODEL,
            "groq_model":       settings.GROQ_MODEL,
            "gemini_model":     settings.GEMINI_MODEL,
        },
        "rag": {
            "embedding_model":     settings.EMBEDDING_MODEL,
            "chunk_size":          settings.CHUNK_SIZE,
            "chunk_overlap":       settings.CHUNK_OVERLAP,
            "top_k":               settings.RAG_TOP_K,
            "score_threshold":     settings.RAG_SCORE_THRESHOLD,
            "max_context_tokens":  settings.MAX_CONTEXT_TOKENS,
        },
        "limits": {
            "rate_limit_per_minute":       settings.RATE_LIMIT_PER_MINUTE,
            "rate_limit_agent_per_minute": settings.RATE_LIMIT_AGENT_PER_MINUTE,
            "max_resume_size_mb":          settings.MAX_RESUME_SIZE_MB,
            "allowed_resume_types":        settings.ALLOWED_RESUME_TYPES,
        },
    })


# In-memory override store for runtime-tunable settings (process-lifetime only).
# Note: persisting these to DB/Redis is a future enhancement; for now they apply
# immediately to the running process via the settings singleton attributes that
# support reassignment (non-Pydantic-frozen).
@router.patch("/settings", response_model=APIResponse,
             summary="[Admin] Update runtime-tunable settings (in-memory, this process only)")
def update_settings_view(payload: SettingsUpdateRequest, admin: AdminUser) -> APIResponse:
    updated = {}
    if payload.rag_top_k is not None:
        settings.RAG_TOP_K = payload.rag_top_k
        updated["rag_top_k"] = payload.rag_top_k
    if payload.rag_score_threshold is not None:
        settings.RAG_SCORE_THRESHOLD = payload.rag_score_threshold
        updated["rag_score_threshold"] = payload.rag_score_threshold
    if payload.chunk_size is not None:
        settings.CHUNK_SIZE = payload.chunk_size
        updated["chunk_size"] = payload.chunk_size
    if payload.chunk_overlap is not None:
        settings.CHUNK_OVERLAP = payload.chunk_overlap
        updated["chunk_overlap"] = payload.chunk_overlap
    if payload.rate_limit_per_minute is not None:
        settings.RATE_LIMIT_PER_MINUTE = payload.rate_limit_per_minute
        updated["rate_limit_per_minute"] = payload.rate_limit_per_minute
    if payload.max_resume_size_mb is not None:
        settings.MAX_RESUME_SIZE_MB = payload.max_resume_size_mb
        updated["max_resume_size_mb"] = payload.max_resume_size_mb

    logger.info("admin_settings_updated", updated=updated, by_admin=admin.user_id)
    return APIResponse(
        message="Settings updated for this process. Restart required for permanent persistence via .env.",
        data=updated,
    )


# ═════════════════════════════════════════════════════════════════════════════
# SYSTEM LOGS
# ═════════════════════════════════════════════════════════════════════════════

@router.get("/logs", response_model=APIResponse,
           summary="[Admin] Paginated, filterable system logs (from agent_logs table)")
def get_system_logs(
    admin:      AdminUser,
    db:         DBSession,
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(25, ge=1, le=100),
    level:      Optional[str]  = Query(None, description="success | failed | timeout"),
    search:     Optional[str]  = Query(None, description="Search error messages"),
) -> APIResponse:
    """
    Surfaces agent_logs as system logs (auth/API/system events are logged via
    structlog to stdout — this endpoint surfaces what's queryable from DB).
    """
    from app.models.agent_log import AgentLog, AgentLogStatus

    query = select(AgentLog)
    if level:
        try:
            query = query.where(AgentLog.status == AgentLogStatus(level))
        except ValueError:
            pass
    if search:
        query = query.where(AgentLog.error_message.ilike(f"%{search}%"))

    from sqlalchemy import func as sa_func
    total = db.scalar(select(sa_func.count()).select_from(query.subquery())) or 0
    logs  = db.scalars(
        query.order_by(desc(AgentLog.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return APIResponse(data={
        "total": total,
        "page":  page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "logs": [
            {
                "log_id":        log.log_id,
                "level":         log.status.value if hasattr(log.status, "value") else str(log.status),
                "source":        log.agent_name.value if hasattr(log.agent_name, "value") else str(log.agent_name),
                "message":       log.error_message or "OK",
                "user_id":       log.user_id,
                "latency_ms":    log.latency_ms,
                "created_at":    log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
    })
