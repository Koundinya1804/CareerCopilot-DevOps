"""
app/rag/citations/citation_builder.py
──────────────────────────────────────
Build structured source citations from retrieved chunks.

Features:
  - Deduplicate citations by source file
  - Assign [1], [2], ... citation numbers
  - Build inline-citation text (e.g., "ACID means... [1]")
  - Format citations as Markdown or JSON
"""
from __future__ import annotations

from dataclasses import dataclass

from app.rag.retriever.retriever import RetrievedChunk
from app.rag.kb_categories import KB_CATEGORIES


@dataclass
class Citation:
    number:   int
    filename: str
    category: str
    category_label: str
    source:   str
    score:    float
    excerpt:  str       # first 120 chars of the chunk
    chunk_id: str


def build_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """
    Build a deduplicated, numbered citation list from retrieved chunks.
    Multiple chunks from the same file share one citation number.
    """
    seen:      dict[str, int] = {}   # filename → citation number
    citations: list[Citation] = []
    counter    = 1

    for chunk in chunks:
        fname = chunk.filename or chunk.source or "Unknown Source"

        if fname not in seen:
            seen[fname] = counter
            cat_label   = KB_CATEGORIES.get(chunk.category, None)
            citations.append(Citation(
                number=counter,
                filename=fname,
                category=chunk.category,
                category_label=cat_label.label if cat_label else chunk.category.replace("_", " ").title(),
                source=chunk.source,
                score=chunk.score,
                excerpt=chunk.content[:120].strip(),
                chunk_id=chunk.chunk_id,
            ))
            counter += 1

    return citations


def format_citations_markdown(citations: list[Citation]) -> str:
    """Return a Markdown-formatted references section."""
    if not citations:
        return ""
    lines = ["\n\n---\n**Sources:**"]
    for c in citations:
        lines.append(f"[{c.number}] **{c.category_label}** — `{c.filename}` (relevance: {c.score:.0%})")
    return "\n".join(lines)


def format_citations_json(citations: list[Citation]) -> list[dict]:
    """Return citations as a list of dicts for API responses."""
    return [
        {
            "number":         c.number,
            "filename":       c.filename,
            "category":       c.category,
            "category_label": c.category_label,
            "score":          c.score,
            "excerpt":        c.excerpt,
        }
        for c in citations
    ]


def inject_citation_numbers(
    answer:  str,
    chunks:  list[RetrievedChunk],
    citations: list[Citation],
) -> str:
    """
    Post-process the LLM answer to inject [N] markers where the LLM
    used specific chunks (matched by keyword overlap).
    This is a heuristic — exact citation requires prompting the LLM to output them.
    """
    # Build filename → citation number lookup
    fn_to_num = {c.filename: c.number for c in citations}

    # Simple heuristic: append citation number at first usage of key topic words
    for chunk in chunks:
        fname = chunk.filename or ""
        num   = fn_to_num.get(fname)
        if not num:
            continue

        # Check if chunk content keywords appear in the answer
        keywords = [w for w in chunk.content.split()[:10] if len(w) > 4]
        for kw in keywords:
            if kw in answer and f"[{num}]" not in answer:
                answer = answer.replace(kw, f"{kw} [{num}]", 1)
                break

    return answer
