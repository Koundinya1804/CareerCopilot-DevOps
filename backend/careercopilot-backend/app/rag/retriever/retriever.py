"""
app/rag/retriever/retriever.py
───────────────────────────────
Retrieval logic for the RAG pipeline.

Features:
  - Query expansion (generate multiple phrasings)
  - Maximal Marginal Relevance (MMR) for diversity
  - Cross-category search with category routing
  - Metadata-filtered retrieval
  - Chunk deduplication by source proximity
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_core.documents import Document

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.kb_categories import KB_CATEGORIES
from app.rag.vectorstore.chroma_store import get_vectorstore

logger = get_logger(__name__)


# ── Category router ───────────────────────────────────────────────────────────
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "dbms": [
        "sql", "database", "query", "join", "normalization", "acid", "transaction",
        "index", "nosql", "mongodb", "mysql", "postgresql", "schema", "table",
        "foreign key", "primary key", "stored procedure", "trigger", "view",
    ],
    "operating_systems": [
        "process", "thread", "scheduling", "deadlock", "memory", "paging",
        "virtual memory", "semaphore", "mutex", "ipc", "kernel", "system call",
        "file system", "interrupt", "context switch", "race condition",
    ],
    "computer_networks": [
        "tcp", "udp", "ip", "http", "dns", "osi", "protocol", "socket",
        "routing", "subnet", "bandwidth", "latency", "firewall", "vpn",
        "ssl", "tls", "websocket", "rest api", "grpc", "network",
    ],
    "oop": [
        "class", "object", "inheritance", "polymorphism", "encapsulation",
        "abstraction", "interface", "abstract", "solid", "design pattern",
        "singleton", "factory", "observer", "decorator", "composition",
    ],
    "java": [
        "jvm", "java", "spring", "maven", "gradle", "garbage collection",
        "generics", "collections", "stream api", "lambda", "optional",
        "multithreading", "synchronized", "executor", "hibernate", "jpa",
    ],
    "python": [
        "python", "django", "flask", "fastapi", "pandas", "numpy",
        "decorator", "generator", "comprehension", "gil", "asyncio",
        "pytest", "pip", "virtual environment", "dataclass", "typing",
    ],
    "aptitude": [
        "aptitude", "reasoning", "quantitative", "logical", "number system",
        "percentage", "profit", "loss", "time", "speed", "distance",
        "permutation", "combination", "probability", "series",
    ],
    "hr_questions": [
        "tell me about yourself", "strength", "weakness", "why should we hire",
        "career goals", "team", "conflict", "leadership", "achievement",
        "salary", "notice period", "behavioural", "situational", "hr",
    ],
    "company_guides": [
        "google", "amazon", "microsoft", "infosys", "tcs", "wipro",
        "flipkart", "swiggy", "interview process", "company culture",
        "placement", "campus", "offer", "package", "coding round",
    ],
}


def _route_category(query: str) -> list[str]:
    """
    Infer the most relevant categories for a query using keyword matching.
    Returns up to 3 most relevant categories. Falls back to all categories.
    """
    query_lower = query.lower()
    scores: dict[str, int] = {}

    for cat, keywords in _CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[cat] = score

    if not scores:
        return list(KB_CATEGORIES.keys())

    # Return top-3 categories by keyword match score
    return sorted(scores, key=lambda c: scores[c], reverse=True)[:3]


# ── Query expansion ───────────────────────────────────────────────────────────
def _expand_query(query: str) -> list[str]:
    """
    Generate query variants to improve recall via multiple phrasings.
    Simple rule-based expansion (no LLM cost).
    """
    variants: list[str] = [query]

    # Add "what is / explain / define" variants for short queries
    words = query.split()
    if len(words) <= 4 and not query.lower().startswith(("what", "explain", "how", "why", "define")):
        variants.append(f"what is {query}")
        variants.append(f"explain {query} in detail")
        variants.append(f"definition and example of {query}")

    # Interview-specific variant
    if any(w in query.lower() for w in ["interview", "question", "asked"]):
        variants.append(f"common interview questions about {query.replace('interview', '').strip()}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique[:4]


# ── MMR re-ranker ─────────────────────────────────────────────────────────────
def _mmr_rerank(
    candidates: list[tuple[Document, float]],
    k:          int   = 5,
    lambda_:    float = 0.7,
) -> list[tuple[Document, float]]:
    """
    Maximal Marginal Relevance — balances relevance and diversity.
    lambda_=1.0 → pure similarity; lambda_=0.0 → pure diversity.
    """
    if len(candidates) <= k:
        return candidates

    import numpy as np
    from app.rag.embeddings.embedder import embed_texts

    texts  = [d.page_content for d, _ in candidates]
    scores = [s for _, s in candidates]
    vecs   = embed_texts(texts)

    selected_idx: list[int] = []
    remaining     = list(range(len(candidates)))

    # Always pick the top-ranked first
    best = max(remaining, key=lambda i: scores[i])
    selected_idx.append(best)
    remaining.remove(best)

    while len(selected_idx) < k and remaining:
        sel_vecs = [vecs[i] for i in selected_idx]

        best_mmr = -float("inf")
        best_idx  = remaining[0]

        for i in remaining:
            relevance   = scores[i]
            # Max cosine similarity to any already-selected doc
            max_sim = max(
                float(np.dot(vecs[i], sv) / (np.linalg.norm(vecs[i]) * np.linalg.norm(sv) + 1e-8))
                for sv in sel_vecs
            )
            mmr = lambda_ * relevance - (1 - lambda_) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx  = i

        selected_idx.append(best_idx)
        remaining.remove(best_idx)

    return [candidates[i] for i in selected_idx]


# ── RetrievedChunk dataclass ──────────────────────────────────────────────────
@dataclass
class RetrievedChunk:
    content:    str
    score:      float
    category:   str
    source:     str
    filename:   str
    chunk_id:   str
    chunk_index: int
    metadata:   dict = field(default_factory=dict)


# ── Main retrieval function ───────────────────────────────────────────────────
def retrieve_chunks(
    query:        str,
    categories:   list[str] | None = None,
    k:            int               = settings.RAG_TOP_K,
    score_threshold: float          = settings.RAG_SCORE_THRESHOLD,
    use_mmr:      bool              = True,
    expand_query: bool              = True,
) -> list[RetrievedChunk]:
    """
    Full retrieval pipeline:
      1. Route query to relevant categories
      2. Optionally expand query into multiple phrasings
      3. Similarity search across selected collections
      4. Merge and deduplicate results
      5. MMR re-rank for diversity

    Returns top-k RetrievedChunk objects sorted by relevance.
    """
    store = get_vectorstore()

    # 1. Category routing
    search_cats = categories if categories else _route_category(query)
    logger.info("retrieval_start", query=query[:80], categories=search_cats)

    # 2. Query expansion
    queries = _expand_query(query) if expand_query else [query]

    # 3. Search with all query variants
    raw: list[tuple[Document, float, str]] = []
    seen_ids: set[str] = set()

    for q in queries:
        results = store.multi_category_search(
            q,
            categories=search_cats,
            k=k * 2,
            score_threshold=score_threshold,
        )
        for doc, score, cat in results:
            cid = doc.metadata.get("chunk_id", doc.page_content[:32])
            if cid not in seen_ids:
                seen_ids.add(cid)
                raw.append((doc, score, cat))

    if not raw:
        logger.warning("no_results_retrieved", query=query[:80])
        return []

    # 4. Sort by score, group for MMR
    raw.sort(key=lambda x: x[1], reverse=True)
    candidates = [(doc, score) for doc, score, _ in raw]
    cat_map    = {doc.metadata.get("chunk_id", ""): cat for doc, score, cat in raw}

    # 5. MMR re-rank
    if use_mmr and len(candidates) > k:
        try:
            candidates = _mmr_rerank(candidates, k=k)
        except Exception as exc:
            logger.warning("mmr_rerank_failed", error=str(exc))
            candidates = candidates[:k]
    else:
        candidates = candidates[:k]

    # 6. Build result objects
    results_out: list[RetrievedChunk] = []
    for doc, score in candidates:
        meta = doc.metadata
        cid  = meta.get("chunk_id", "")
        results_out.append(RetrievedChunk(
            content=doc.page_content,
            score=round(score, 4),
            category=cat_map.get(cid, meta.get("category", "unknown")),
            source=meta.get("source", ""),
            filename=meta.get("filename", ""),
            chunk_id=cid,
            chunk_index=int(meta.get("chunk_index", 0)),
            metadata=meta,
        ))

    logger.info("retrieval_complete", query=query[:80], results=len(results_out))
    return results_out


# ── LangChain Retriever adapter ───────────────────────────────────────────────
def get_retriever(
    categories:       list[str] | None = None,
    k:                int               = settings.RAG_TOP_K,
    score_threshold:  float             = settings.RAG_SCORE_THRESHOLD,
):
    """
    Return a LangChain BaseRetriever-compatible object for use in chains.
    """
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.retrievers import BaseRetriever

    class _CareerCopilotRetriever(BaseRetriever):
        def _get_relevant_documents(
            self,
            query: str,
            *,
            run_manager: CallbackManagerForRetrieverRun,
        ) -> list[Document]:
            chunks = retrieve_chunks(query, categories=categories, k=k,
                                     score_threshold=score_threshold)
            return [
                Document(page_content=c.content, metadata={**c.metadata, "score": c.score})
                for c in chunks
            ]

    return _CareerCopilotRetriever()
