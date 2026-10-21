"""
app/langgraph/nodes/supervisor.py
──────────────────────────────────
Supervisor Agent Node — the entry point of the graph.

Responsibilities:
  1. Classify user intent from the query
  2. Determine which specialist agent to route to
  3. Extract routing metadata (requires_resume, is_multi_step, etc.)
  4. Handle loop detection and safety ceiling

Routing strategy:
  - Rule-based keyword routing first (fast, free, deterministic). When a
    query matches more than one pattern, the match with the HIGHEST
    confidence wins — this is unchanged from the original implementation.
    What changed is which patterns exist and what confidence each carries,
    so that specific/unambiguous signals (CS jargon, company+interview,
    resume/skill-gap keywords) reliably outrank generic ones (the broad
    "what is / explain" catch-all, which is now the lowest-confidence rule
    on purpose).
  - Anything that matches no rule falls through to rag_agent with intent
    "general_chat" — there is no separate "general LLM" node in this graph;
    rag_agent IS the general-LLM handler when ChromaDB has nothing relevant
    (see app/rag/chains/rag_chain.py's no-context fallback). This keeps the
    existing 5-agent architecture intact while still giving every query
    somewhere sensible to land.
  - Confidence score is logged for analytics/debugging visibility into why
    a routing decision was made.

Intent → Agent mapping (highest-confidence matching rule wins):
  resume_*                          → resume_agent
  skill_gap_*                       → skill_gap_agent
  interview_* / company+interview   → interview_agent
  cs_concept (java/python/dbms/...) → rag_agent   (knowledge-base lookup)
  career_* / salary / companies /
    placements / internships /
    roadmaps / job roles            → career_agent
  everything else                   → rag_agent, intent="general_chat"
                                       (general knowledge / casual chat —
                                        rag_agent falls back to an
                                        unrestricted LLM answer when no KB
                                        chunks are relevant)
"""
from __future__ import annotations

import re
import time

from app.core.logging import get_logger
from app.langgraph.state import AgentName, AgentState

logger = get_logger(__name__)

# ── Intent keyword map ────────────────────────────────────────────────────────
# Evaluated as "highest confidence match among all patterns that match" — so
# the confidence numbers ARE the priority order. Keep that in mind when
# editing: a query matching two rules always goes to whichever has the
# higher number here, regardless of list order.
_INTENT_MAP: list[tuple[str, AgentName, str, float]] = [
    # (regex pattern, agent, intent_label, confidence)

    # Resume agent
    (r"\b(analyse|analyze|review|score|ats|my resume|upload resume|check resume|resume feedback)\b",
     "resume_agent", "resume_analysis", 0.95),

    # Skill gap agent
    (r"\b(skill gap|missing skills|what skills|skills needed|skills for|skills required|upskill|learning path|skill match)\b",
     "skill_gap_agent", "skill_gap_analysis", 0.93),

    # Company-specific interview prep — must outrank both the generic
    # interview rule and the career rule, since it matches company names
    # that also appear in career-ish phrasing ("Google's hiring process").
    (r"\b(google|amazon|microsoft|meta|netflix|apple|nvidia|openai|adobe|salesforce|oracle|"
     r"walmart|tcs|infosys|wipro|accenture|capgemini|flipkart|swiggy|zomato)\b.*"
     r"\b(interview|hire|hiring|process|round|rounds)\b",
     "interview_agent", "company_interview_prep", 0.96),

    # Interview agent — general
    (r"\b(interview|mock interview|practice interview|interview question|prepare for interview|interview coaching|interview tips|interview prep)\b",
     "interview_agent", "interview_coaching", 0.92),

    # Computer-science / programming concepts — unambiguous jargon that is
    # essentially never used outside a CS-concept question, so it's safe to
    # match standalone with high confidence.
    (r"\b(dbms|normalization|indexing|deadlock|paging|semaphore|multithreading|"
     r"osi model|tcp|udp|dns|"
     r"polymorphism|encapsulation|abstraction|"
     r"dsa|linked list|binary tree|graph traversal|"
     r"time complexity|space complexity|big o)\b",
     "rag_agent", "cs_concept_qa", 0.94),

    # CS-concept terms that ARE ambiguous on their own (a bare "python" or
    # "database" can just as easily appear inside a career-fit sentence like
    # "what career suits my Python skills") — these only count as a
    # knowledge-base question when paired with explanatory framing.
    (r"\b(what is|explain|how does|define|difference between|how to use)\b.*"
     r"\b(java|python|c\+\+|database|sql|operating system|process scheduling|thread|"
     r"computer network|networking|http|oop|object[- ]oriented|inheritance|"
     r"data structure|algorithm|array|stack|queue|sorting|searching algorithm|recursion|"
     r"aptitude|reasoning question)\b",
     "rag_agent", "cs_concept_qa", 0.94),

    # Explicit knowledge-base / document search
    (r"\b(knowledge base|uploaded documents?|my documents?|search (the )?kb|search documents?)\b",
     "rag_agent", "kb_search", 0.94),

    # Career agent — advice, roles, salary, placements, companies (outside an
    # interview-process context), internships, roadmaps. Salary/package/CTC
    # terms live HERE, not on rag_agent — pay is a career-planning question,
    # not a knowledge-base lookup.
    (r"\b(career|recommend|best role|which role|job role|job fit|career path|career advice|"
     r"what career|suitable for me|career recommendation|career guidance|"
     r"salary|pay|compensation|package|lpa|ctc|wage|stipend|"
     r"placement|placements|hiring trend|internship|internships|"
     r"roadmap|career roadmap|growth path|promotion path)\b",
     "career_agent", "career_recommendation", 0.90),

    # General knowledge / explanatory catch-all — deliberately the LOWEST
    # confidence rule so anything more specific above always wins. Still
    # routes to rag_agent, which now falls back to an unrestricted LLM
    # answer for anything ChromaDB has no coverage for (see rag_chain.py),
    # so this doubles as the "general chat" handler for phrased-as-a-
    # question queries like "what is the population of India".
    (r"\b(what is|explain|how does|define|tell me about|difference between|when to use|why is|how to|example of)\b",
     "rag_agent", "knowledge_qa", 0.75),
]

# ── Multi-step detection patterns ─────────────────────────────────────────────
_MULTI_STEP_PATTERNS = [
    r"\band\s+(then|also|after|give)\b",
    r"\b(both|all of the above|everything|full analysis|complete)\b",
    r"\b(plus|additionally|also tell|also show)\b",
]

# ── Resume requirement patterns ────────────────────────────────────────────────
_RESUME_REQUIRED = [
    r"\bmy resume\b", r"\bmy skills\b", r"\bmy profile\b",
    r"\bmy background\b", r"\banalyse me\b", r"\bfor me\b",
    r"\bmy experience\b",
]


# ── Rule-based router ─────────────────────────────────────────────────────────
def _rule_based_route(query: str) -> tuple[AgentName, str, float] | None:
    """Return (agent, intent, confidence) or None if no confident match."""
    q = query.lower()
    best: tuple[AgentName, str, float] | None = None

    for pattern, agent, intent, conf in _INTENT_MAP:
        if re.search(pattern, q, re.IGNORECASE):
            if best is None or conf > best[2]:
                best = (agent, intent, conf)

    return best


def _detect_multi_step(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q, re.IGNORECASE) for p in _MULTI_STEP_PATTERNS)


def _detect_resume_required(query: str) -> bool:
    q = query.lower()
    return any(re.search(p, q, re.IGNORECASE) for p in _RESUME_REQUIRED)


# ── Ambiguous-query fallback ───────────────────────────────────────────────────
def _default_route(query: str) -> tuple[AgentName, str, float]:
    """
    Used when no rule-based pattern matches at all — e.g. "Who is Sundar
    Pichai?", "Tell me a joke", general chit-chat, or any query that doesn't
    contain an obvious resume/skill-gap/career/interview/CS-concept signal.

    There is no separate "general LLM" node in this graph (see module
    docstring), so this always lands on rag_agent. That is correct: rag_node
    searches ChromaDB, and when nothing relevant is found (which is the
    normal case for "who is X" / current-events / casual-chat queries),
    app/rag/chains/rag_chain.py answers the question directly using the
    LLM's own general knowledge instead of the KB-only refusal message.

    This intentionally replaces a previous implementation that shelled out
    to Gemini for a "smarter" classification — that call required
    GEMINI_API_KEY, which this deployment doesn't set (the app runs on
    Groq), so it silently failed on every single call and fell back to this
    exact same rag_agent default anyway. Removing it cuts one dead network
    call out of every unmatched query with no change in behaviour.
    """
    return "rag_agent", "general_chat", 0.5


# ── Supervisor node ───────────────────────────────────────────────────────────
def supervisor_node(state: AgentState) -> AgentState:
    """
    LangGraph node: classify intent, choose next agent, return state update.
    This is the ENTRY point of the graph — called first on every invocation.
    """
    t0    = time.monotonic()
    query = state.get("original_query", "")

    # Safety: loop detection
    iteration = (state.get("iteration") or 0) + 1
    max_iter  = state.get("max_iterations") or 5
    if iteration > max_iter:
        logger.warning("max_iterations_reached", iteration=iteration, session=state.get("session_id"))
        return {
            **state,
            "next_agent":    "END",
            "routing_reason": f"Safety ceiling reached ({max_iter} iterations).",
            "has_error":     True,
            "error":         "Maximum agent iterations reached. Please refine your query.",
            "iteration":     iteration,
        }

    # Rule-based routing first
    route_result = _rule_based_route(query)
    if route_result:
        next_agent, intent, confidence = route_result
        routing_reason = f"Keyword match → {intent} (confidence {confidence:.0%})"
    else:
        next_agent, intent, confidence = _default_route(query)
        routing_reason = f"No keyword match → default general_chat routing to {next_agent}"

    is_multi_step    = _detect_multi_step(query)
    requires_resume  = _detect_resume_required(query)

    # Log the routing decision
    logger.info(
        "supervisor_routed",
        session=state.get("session_id"),
        query_preview=query[:60],
        next_agent=next_agent,
        intent=intent,
        confidence=confidence,
        iteration=iteration,
    )

    elapsed = int((time.monotonic() - t0) * 1000)

    return {
        **state,
        "next_agent":      next_agent,
        "routing_reason":  routing_reason,
        "intent":          intent,
        "confidence":      confidence,
        "is_multi_step":   is_multi_step,
        "requires_resume": requires_resume,
        "iteration":       iteration,
        "agent_chain":     (state.get("agent_chain") or []) + ["supervisor"],
        "total_latency_ms": (state.get("total_latency_ms") or 0) + elapsed,
    }


# ── Routing conditional ────────────────────────────────────────────────────────
def route_after_supervisor(state: AgentState) -> AgentName:
    """
    LangGraph conditional edge function.
    Returns the name of the next node to visit.
    """
    if state.get("has_error"):
        return "END"
    return state.get("next_agent") or "rag_agent"
