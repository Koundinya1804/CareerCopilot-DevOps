"""
app/rag/vectorstore/index_tracker.py
──────────────────────────────────────
Tracks "last indexed at" per KB category.

There's no existing DB table for this and adding one is a bigger schema
change than this needs — so it's a small JSON side-file next to the Chroma
persist directory. Every successful ingestion (category-level, single
document, bulk "reindex all", or rename-triggered re-ingest) calls
`record_indexed(category)`. The ChromaDB admin page reads it back via
`get_last_indexed(category)` to show "Last indexed" per collection.

Not meant to be a source of truth for anything beyond that display — if the
file is missing or corrupted, callers just get None / no data.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_LOCK = Lock()


def _tracker_path() -> Path:
    p = Path(settings.CHROMA_PERSIST_DIR) / "_meta"
    p.mkdir(parents=True, exist_ok=True)
    return p / "last_indexed.json"


def _read_all() -> dict[str, str]:
    path = _tracker_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        logger.warning("index_tracker_read_failed", path=str(path))
        return {}


def record_indexed(category: str) -> None:
    """Mark `category` as indexed right now. Best-effort — never raises."""
    try:
        with _LOCK:
            data = _read_all()
            data[category] = datetime.utcnow().isoformat() + "Z"
            _tracker_path().write_text(json.dumps(data, indent=2))
    except Exception as exc:
        logger.warning("index_tracker_write_failed", category=category, error=str(exc))


def get_last_indexed(category: str) -> str | None:
    return _read_all().get(category)


def get_all_last_indexed() -> dict[str, str]:
    return _read_all()
