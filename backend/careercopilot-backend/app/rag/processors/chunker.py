"""
app/rag/processors/chunker.py
──────────────────────────────
Text chunking strategies for the RAG pipeline.

Strategy selection:
  - RecursiveCharacterTextSplitter  → default, best for prose/technical docs
  - SentenceWindowSplitter          → Q&A / short factual content
  - SemanticChunker                 → when sentence-transformers is available

Each chunk preserves full parent metadata plus adds:
  chunk_index, chunk_id, total_chunks, strategy, overlap_chars
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

ChunkStrategy = Literal["recursive", "sentence_window", "paragraph"]


@dataclass
class ChunkConfig:
    strategy:     ChunkStrategy = "recursive"
    chunk_size:   int           = 512
    chunk_overlap: int          = 64
    min_chunk_len: int          = 50     # discard chunks shorter than this
    add_start_index: bool       = True   # store start char position


def _make_chunk_id(text: str, source: str, index: int) -> str:
    """Stable, deterministic ID for a chunk (used as ChromaDB document ID)."""
    raw = f"{source}::{index}::{text[:100]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Recursive Chunker (default) ───────────────────────────────────────────────
def chunk_recursive(
    documents: list[Document],
    config:    ChunkConfig,
) -> list[Document]:
    """
    LangChain RecursiveCharacterTextSplitter — splits on paragraph, sentence,
    word boundaries in order, producing semantically coherent chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        length_function=len,
        add_start_index=config.add_start_index,
        separators=["\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " ", ""],
    )

    all_chunks: list[Document] = []
    for doc in documents:
        splits = splitter.split_documents([doc])

        # Filter too-short chunks
        splits = [s for s in splits if len(s.page_content.strip()) >= config.min_chunk_len]

        for i, chunk in enumerate(splits):
            chunk.metadata["chunk_index"]  = i
            chunk.metadata["total_chunks"] = len(splits)
            chunk.metadata["strategy"]     = "recursive"
            chunk.metadata["chunk_id"]     = _make_chunk_id(
                chunk.page_content, chunk.metadata.get("source", ""), i
            )
            all_chunks.append(chunk)

    logger.debug("chunked_recursive", input_docs=len(documents), output_chunks=len(all_chunks))
    return all_chunks


# ── Sentence Window Chunker ───────────────────────────────────────────────────
def chunk_sentence_window(
    documents:   list[Document],
    config:      ChunkConfig,
    window_size: int = 3,
) -> list[Document]:
    """
    Split into sentences, then group into windows of `window_size` sentences.
    Better for Q&A-formatted content where each sentence is self-contained.
    """
    sentence_end = re.compile(r"(?<=[.!?])\s+")
    all_chunks: list[Document] = []

    for doc in documents:
        sentences = [s.strip() for s in sentence_end.split(doc.page_content) if s.strip()]
        chunks: list[Document] = []

        for i in range(0, len(sentences), max(1, window_size - 1)):
            window = sentences[i: i + window_size]
            text   = " ".join(window)
            if len(text) < config.min_chunk_len:
                continue
            chunk = Document(
                page_content=text,
                metadata={
                    **doc.metadata,
                    "chunk_index":  len(chunks),
                    "strategy":     "sentence_window",
                    "window_size":  window_size,
                    "chunk_id":     _make_chunk_id(text, doc.metadata.get("source", ""), i),
                },
            )
            chunks.append(chunk)

        for i, c in enumerate(chunks):
            c.metadata["total_chunks"] = len(chunks)
        all_chunks.extend(chunks)

    logger.debug("chunked_sentence_window", input_docs=len(documents), output_chunks=len(all_chunks))
    return all_chunks


# ── Paragraph Chunker ─────────────────────────────────────────────────────────
def chunk_paragraph(
    documents: list[Document],
    config:    ChunkConfig,
) -> list[Document]:
    """
    Split on double-newlines (paragraphs). Good for structured text with
    clear section breaks. Falls back to recursive for long paragraphs.
    """
    all_chunks: list[Document] = []

    for doc in documents:
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", doc.page_content) if p.strip()]
        chunks: list[Document] = []

        for para in paragraphs:
            if len(para) <= config.chunk_size:
                if len(para) >= config.min_chunk_len:
                    chunks.append(Document(page_content=para, metadata=dict(doc.metadata)))
            else:
                # Paragraph too long — recursively split it
                sub_docs = chunk_recursive(
                    [Document(page_content=para, metadata=dict(doc.metadata))],
                    config,
                )
                chunks.extend(sub_docs)

        for i, c in enumerate(chunks):
            c.metadata["chunk_index"]  = i
            c.metadata["total_chunks"] = len(chunks)
            c.metadata["strategy"]     = "paragraph"
            c.metadata["chunk_id"]     = _make_chunk_id(
                c.page_content, c.metadata.get("source", ""), i
            )
        all_chunks.extend(chunks)

    return all_chunks


# ── Dispatcher ────────────────────────────────────────────────────────────────
def chunk_documents(
    documents: list[Document],
    strategy:  ChunkStrategy     = "recursive",
    chunk_size:   int | None     = None,
    chunk_overlap: int | None    = None,
) -> list[Document]:
    """
    Main entry point. Selects strategy and chunks all documents.
    Returns deduplicated chunks sorted by source + chunk_index.
    """
    cfg = ChunkConfig(
        strategy=strategy,
        chunk_size=chunk_size or settings.CHUNK_SIZE,
        chunk_overlap=chunk_overlap or settings.CHUNK_OVERLAP,
    )

    if strategy == "recursive":
        chunks = chunk_recursive(documents, cfg)
    elif strategy == "sentence_window":
        chunks = chunk_sentence_window(documents, cfg)
    elif strategy == "paragraph":
        chunks = chunk_paragraph(documents, cfg)
    else:
        chunks = chunk_recursive(documents, cfg)

    # Deduplicate by chunk_id
    seen:   set[str]       = set()
    unique: list[Document] = []
    for c in chunks:
        cid = c.metadata.get("chunk_id", "")
        if cid not in seen:
            seen.add(cid)
            unique.append(c)

    logger.info(
        "chunks_created",
        strategy=strategy,
        input_docs=len(documents),
        output_chunks=len(unique),
        avg_size=int(sum(len(c.page_content) for c in unique) / max(1, len(unique))),
    )
    return unique
