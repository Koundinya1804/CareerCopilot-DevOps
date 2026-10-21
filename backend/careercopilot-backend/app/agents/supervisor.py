"""
app/langgraph/nodes/supervisor.py
──────────────────────────────────
Supervisor Agent Node — the entry point of the LangGraph.

Responsibilities:
  1. Classify user intent from the query
  2. Determine which specialist agent to route to
  3. Extract routing metadata (requires_resume, is_multi_step, etc.)
  4. Handle loop detection and safety ceiling

Routing strategy:
  - Rule-based keyword routing first (fast, free, deterministic)
  - LLM fallback via centralised provider for ambiguous queries
  - Confidence score indicates certainty of routing decision

Intent → Agent mapping:
  resume_*        → resume_agent
  skill_gap_*     → skill_gap_agent
  career_*        → career_agent
  interview_*     → interview_agent
  rag_* / qa_*    → rag_agent
  multi_step      → resume_agent first (chain begins)
"""
from __future__ import annotations

import time

from app.core.config import settings
from app.core.logging import get_logger
from app.core.llm_provider import call_llm, parse_llm_json
from app.langgraph.state import AgentName, AgentState
import re

logger = get_logger(__name__)

# ── Intent keyword map ────────────────────────────────────────────────────────
_INTENT_MAP: list[tuple[str, AgentName, str, float]] = [
    # Resume agent
    (r"\b(analyse|analyze|review|score|ats|my resume|upload resume|check resume|resume feedback)\b",
     "resume_agent", "resume_analysis", 0.95),

    # Skill gap agent
    (r"\b(skill gap|missing skills|what skills|skills needed|skills for|skills required|upskill|learning path|skill match)\b",
     "skill_gap_agent", "skill_gap_analysis", 0.93),

    # Career recommendation agent
    (r"\b(career|recommend|best role|which role|job fit|career path|career advice|what career|suitable for me|career recommendation|career guidance)\b",
     "career_agent", "career_recommendation", 0.90),

    # Interview agent
    (r"\b(interview|mock interview|practice interview|interview question|prepare for interview|interview coaching|interview tips|interview prep)\b",
     "interview_agent", "interview_coaching", 0.92),

    # RAG agent — general Q&A
    (r"\b(what is|explain|how does|define|tell me about|difference between|when to use|why is|how to|example of)\b",
     "rag_agent", "knowledge_qa", 0.80),

    # Salary queries → RAG
    (r"\b(salary|pay|compensation|package|lpa|ctc|wage)\b",
     "rag_agent", "salary_query", 0.85),

    # Company-specific → interview
    (r"\b(google|amazon|microsoft|tcs|infosys|wipro|flipkart|swiggy)\b.*\b(interview|hire|hiring|process|round)\b",
     "interview_agent", "company_interview_prep", 0.88),
]

# ── Multi-step detection ──────────────────────────────────────────────────────
_MULTI_STEP_PATTERNS = [
    r"\band\s+(then|also|after|give)\b",
    r"\b(both|all of the above|everything|full analysis|complete)\b",
    r"\b(plus|additionally|also tell|also show)\b",
]

# ── Resume requirement detection ──────────────────────────────────────────────
_RESUME_REQUIRED = [
    r"\bmy resume\b", r"\bmy skills\b", r"\bmy profile\b",
    r"\bmy background\b", r"\banalyse me\b", r"\bfor me\b",
    r"\bmy experience\b",
]


# ── Rule-based router ─────────────────────────────────────────────────────────
def _rule_based_route(query: str) -> tuple[AgentName, str, float] | None:
    """Return (agent, intent, confidence) or None if no confident match."""
    q    = query.lower()
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


# ── LLM fallback router (uses centralised provider — Groq by default) ─────────
def _llm_route(query: str) -> tuple[AgentName, str, float]:
    """
    Use the centralised LLM provider for ambiguous queries when
    rule-based routing fails.  Falls back to rag_agent on error.
    """
    prompt = f"""You are a routing agent for CareerCopilot AI. Classify this user query and choose the best agent.

USER QUERY: "{query}"

AGENTS:
- resume_agent: Analyse resume, ATS score, resume feedback, skills extraction
- skill_gap_agent: Skill gaps for a target role, missing skills, learning priorities
- career_agent: Career recommendations, best-fit roles, career path advice
- interview_agent: Mock interviews, interview questions, interview preparation
- rag_agent: General knowledge Q&A about CS topics, salary, companies, HR questions

Return JSON only (no extra text):
{{"agent": "agent_name", "intent": "intent_label", "confidence": 0.85, "reasoning": "one sentence"}}"""

    try:
        raw, _ = call_llm(
            prompt,
            temperature=0.1,
            max_tokens=200,
            json_mode=True,
        )
        data  = parse_llm_json(raw)
        if not isinstance(data, dict):
            raise ValueError("non-dict response")

        agent = data.get("agent", "rag_agent")
        valid = {"resume_agent", "skill_gap_agent", "career_agent", "interview_agent", "rag_agent"}
        if agent not in valid:
            agent = "rag_agent"

        return agent, data.get("intent", "general"), float(data.get("confidence", 0.6))  # type: ignore[return-value]

    except RuntimeError:
        # LLM provider not configured — silently default to RAG
        logger.warning("llm_routing_unavailable_defaulting_to_rag")
        return "rag_agent", "knowledge_qa", 0.5

    except Exception as exc:
        logger.warning("llm_routing_failed", error=str(exc))
        return "rag_agent", "knowledge_qa", 0.5


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
        logger.warning("max_iterations_reached", iteration=iteration,
                       session=state.get("session_id"))
        return {
            **state,
            "next_agent":    "END",
            "routing_reason": f"Safety ceiling reached ({max_iter} iterations).",
            "has_error":     True,
            "error":         "Maximum agent iterations reached. Please refine your query.",
            "iteration":     iteration,
        }

    # 1. Rule-based routing (free, instant, deterministic)
    route_result = _rule_based_route(query)
    if route_result:
        next_agent, intent, confidence = route_result
        routing_reason = f"Keyword match → {intent} (confidence {confidence:.0%})"
    else:
        # 2. LLM fallback via centralised provider (Groq by default)
        next_agent, intent, confidence = _llm_route(query)
        routing_reason = (
            f"{settings.DEFAULT_LLM_PROVIDER.upper()} routing → "
            f"{intent} (confidence {confidence:.0%})"
        )

    is_multi_step   = _detect_multi_step(query)
    requires_resume = _detect_resume_required(query)

    logger.info(
        "supervisor_routed",
        session=state.get("session_id"),
        query_preview=query[:60],
        next_agent=next_agent,
        intent=intent,
        confidence=confidence,
        iteration=iteration,
        provider=settings.DEFAULT_LLM_PROVIDER,
    )

    elapsed = int((time.monotonic() - t0) * 1000)

    return {
        **state,
        "next_agent":       next_agent,
        "routing_reason":   routing_reason,
        "intent":           intent,
        "confidence":       confidence,
        "is_multi_step":    is_multi_step,
        "requires_resume":  requires_resume,
        "iteration":        iteration,
        "agent_chain":      (state.get("agent_chain") or []) + ["supervisor"],
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
