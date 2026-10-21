"""
app/rag/chains/rag_chain.py
────────────────────────────
Complete RAG chain — LLM provider-agnostic.

Pipeline:
  Query → Retrieve → Build Prompt → LLM (via centralised provider) → Parse → Cite → Return

Features:
  - Streaming support (token-by-token SSE)
  - Conversation history (multi-turn)
  - Category-scoped queries
  - Faithfulness guardrails (answers must be grounded in context)
  - Fallback to "I don't know" when context is insufficient
  - Provider-agnostic: Groq by default, falls back to mock in dev mode
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.core.logging import get_logger
from app.core.llm_provider import get_llm
from app.rag.citations.citation_builder import (
    build_citations,
    format_citations_json,
    format_citations_markdown,
    inject_citation_numbers,
)
from app.rag.retriever.retriever import RetrievedChunk, retrieve_chunks

logger = get_logger(__name__)


# ── Response dataclass ────────────────────────────────────────────────────────

@dataclass
class RAGResponse:
    answer:      str
    citations:   list[dict] = field(default_factory=list)
    chunks_used: int        = 0
    categories:  list[str]  = field(default_factory=list)
    model_used:  str        = ""
    latency_ms:  int        = 0
    tokens_used: int        = 0
    query:       str        = ""
    # True unless the LLM call itself failed — this is "did we produce a
    # real answer", NOT "did retrieval find KB chunks". A general-knowledge
    # fallback answer (no chunks, but a normal successful LLM response) is
    # has_answer=True, answered_from_kb=False.
    has_answer:  bool       = True
    answered_from_kb: bool  = True


# ── System prompts ────────────────────────────────────────────────────────────
# Two modes:
#   1. _SYSTEM_PROMPT          — used when ChromaDB returned relevant chunks.
#                                 Answers must stay grounded in that context.
#   2. _GENERAL_FALLBACK_PROMPT — used when retrieval found nothing relevant.
#                                 The knowledge-base restriction is dropped and
#                                 the model answers normally from its own
#                                 knowledge, exactly like a general assistant.
#                                 This is what lets "who is X" / current-events
#                                 / casual-chat questions get a real answer
#                                 instead of a canned "not in my knowledge
#                                 base" refusal.

_SYSTEM_PROMPT = """You are CareerCopilot AI, an expert career guidance assistant specialising in technical interview preparation for software engineering roles.

Your knowledge covers: DBMS, Operating Systems, Computer Networks, OOP, Java, Python, Aptitude & Reasoning, HR/Behavioural interviews, and Company-specific placement guides.

## RULES
1. Answer using the provided context as your primary source. It is safe to add brief general knowledge to clarify or complete an answer, but the provided context should drive the core of your answer.
2. For technical topics: provide clear definitions, examples, and where applicable, code snippets.
3. For HR questions: provide structured STAR-method answers with realistic examples.
4. For aptitude: show step-by-step working.
5. Keep answers concise but complete. Use bullet points and headers for clarity.
6. When citing, reference source numbers as [1], [2] etc. at the end of sentences.
7. Always end with 1-2 related follow-up questions the user might want to explore.

## CONTEXT
{context}
"""

_GENERAL_FALLBACK_PROMPT = """You are CareerCopilot AI, a helpful, knowledgeable assistant for students and job-seekers in tech.

A search of the internal knowledge base found nothing relevant to this question, so answer it normally using your own general knowledge — the way any capable assistant would. This includes general-knowledge questions (people, companies, current events, technology, definitions), casual conversation, and anything else outside the app's DBMS/OS/Networks/OOP/Java/Python/HR knowledge base.

## RULES
1. Answer directly and naturally — do not mention a "knowledge base" or apologise for not finding documents; the user should not be able to tell this is a fallback path.
2. Be accurate. If you are genuinely unsure or the question needs up-to-date information you may not have, say so plainly rather than guessing.
3. Keep the tone friendly and concise. Match the register of the question — a joke gets a short, fun answer; a factual question gets a clear, direct one.
4. Do not fabricate citations or reference numbers — there is no source context for this answer.
"""


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context(chunks: list[RetrievedChunk]) -> str:
    """
    Format retrieved chunks into a numbered context block.
    Each chunk is labelled with its citation number and category.
    """
    if not chunks:
        return "No relevant context found in the knowledge base."

    citations  = build_citations(chunks)
    fn_to_num  = {c.filename: c.number for c in citations}

    parts: list[str] = []
    for chunk in chunks:
        num = fn_to_num.get(chunk.filename or "", "?")
        parts.append(
            f"[{num}] ({chunk.category.replace('_', ' ').title()} | {chunk.filename})\n"
            f"{chunk.content}\n"
        )

    return "\n---\n".join(parts)


# ── Mock answer (dev mode — no API key configured) ────────────────────────────

def _mock_answer(query: str, context: str) -> str:
    return (
        f"**[DEV MODE — LLM provider not configured]**\n\n"
        f"Your question: *{query}*\n\n"
        f"Context retrieved ({len(context.split())} words from knowledge base).\n\n"
        f"Configure `GROQ_API_KEY` (or `GEMINI_API_KEY`) in `.env` and set "
        f"`DEFAULT_LLM_PROVIDER=groq` to get real AI-generated answers.\n\n"
        f"**Follow-up questions:**\n"
        f"- What are the key concepts related to this topic?\n"
        f"- How is this applied in real interviews?"
    )


# ── Main RAG function ─────────────────────────────────────────────────────────

def get_rag_chain(
    query:           str,
    categories:      list[str] | None = None,
    chat_history:    list[dict] | None = None,
    k:               int               = settings.RAG_TOP_K,
    score_threshold: float             = settings.RAG_SCORE_THRESHOLD,
) -> RAGResponse:
    """
    Execute the full RAG pipeline synchronously.

    Args:
        query:          User question
        categories:     Limit retrieval to specific KB categories (None = auto-route)
        chat_history:   Prior turns [{"role": "user"/"assistant", "content": "..."}]
        k:              Number of chunks to retrieve
        score_threshold: Minimum relevance score to include a chunk
    """
    t0 = time.monotonic()

    # 1. Retrieve relevant chunks
    chunks = retrieve_chunks(
        query,
        categories=categories,
        k=k,
        score_threshold=score_threshold,
    )
    used_categories = list({c.category for c in chunks})

    # 2. Build context + citations
    context        = _build_context(chunks)
    citations_objs = build_citations(chunks)

    # No relevant chunks → drop the KB-only restriction and let the model
    # answer as a general assistant instead of refusing.
    system_prompt = (
        _SYSTEM_PROMPT.format(context=context) if chunks
        else _GENERAL_FALLBACK_PROMPT
    )

    # 3. Get LLM from centralised provider (Groq by default)
    llm = get_llm(streaming=False, temperature=0.2, max_tokens=2048)

    call_succeeded = True
    if llm is None:
        answer = _mock_answer(query, context)
        tokens = 0
    else:
        try:
            messages = [SystemMessage(content=system_prompt)]
            for turn in (chat_history or []):
                if turn.get("role") == "user":
                    messages.append(HumanMessage(content=turn["content"]))
                elif turn.get("role") == "assistant":
                    messages.append(AIMessage(content=turn["content"]))
            messages.append(HumanMessage(content=query))

            response = llm.invoke(messages)
            answer   = response.content if hasattr(response, "content") else str(response)

            # Token count — attribute name varies by provider
            usage  = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {}).get("usage", {})
            tokens = (
                getattr(usage, "total_tokens", None)
                or (usage.get("total_tokens") if isinstance(usage, dict) else None)
                or 0
            )
        except Exception as exc:
            logger.error("rag_chain_llm_error", error=str(exc),
                         provider=settings.DEFAULT_LLM_PROVIDER)
            answer = f"I encountered an error generating the answer: {exc}"
            tokens = 0
            call_succeeded = False

    # 4. Inject citation markers and append references (no-op when there are
    # no citations, i.e. the general-fallback path)
    answer = inject_citation_numbers(answer, chunks, citations_objs)
    answer += format_citations_markdown(citations_objs)

    return RAGResponse(
        answer=answer,
        citations=format_citations_json(citations_objs),
        chunks_used=len(chunks),
        categories=used_categories,
        model_used=settings.active_model,
        latency_ms=int((time.monotonic() - t0) * 1000),
        tokens_used=tokens,
        query=query,
        has_answer=call_succeeded,
        answered_from_kb=bool(chunks),
    )


# ── Streaming RAG (for SSE endpoints) ────────────────────────────────────────

def stream_rag_chain(
    query:        str,
    categories:   list[str] | None = None,
    chat_history: list[dict] | None = None,
    k:            int               = settings.RAG_TOP_K,
) -> Iterator[str]:
    """
    Streaming version of get_rag_chain.
    Yields text tokens for Server-Sent Events.

    Usage:
        for token in stream_rag_chain(query):
            yield f"data: {token}\\n\\n"
    """
    # Retrieval must complete before streaming starts
    chunks         = retrieve_chunks(query, categories=categories, k=k)
    context        = _build_context(chunks)
    citations_objs = build_citations(chunks)
    system_prompt  = (
        _SYSTEM_PROMPT.format(context=context) if chunks
        else _GENERAL_FALLBACK_PROMPT
    )

    # Get streaming-capable LLM from centralised provider
    llm = get_llm(streaming=True, temperature=0.2, max_tokens=2048)

    if llm is None:
        yield _mock_answer(query, context)
        yield format_citations_markdown(citations_objs)
        return

    messages = [SystemMessage(content=system_prompt)]
    for turn in (chat_history or []):
        if turn.get("role") == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn.get("role") == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=query))

    try:
        for chunk in llm.stream(messages):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            if token:
                yield token
        # Append citations after the last token
        yield format_citations_markdown(citations_objs)

    except Exception as exc:
        logger.error("streaming_rag_error", error=str(exc),
                     provider=settings.DEFAULT_LLM_PROVIDER)
        yield f"\n\n[Error during streaming: {exc}]"
