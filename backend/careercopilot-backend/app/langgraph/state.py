"""
app/langgraph/state.py
───────────────────────
LangGraph shared state schema.

AgentState is the single typed dict that flows through every node in the graph.
Each node reads from it and returns a partial update — LangGraph merges these
updates automatically (reducer pattern).

Design principles:
  - Immutable inputs (user_id, session_id, original_query never mutated)
  - Agents write to their own namespaced output field
  - Supervisor writes to routing fields only
  - Memory fields accumulate across multi-turn conversations
  - Error fields capture failures without crashing the graph
"""
from __future__ import annotations

from typing import Annotated, Any, Literal
from typing_extensions import TypedDict


# ── Message accumulator (append-only) ────────────────────────────────────────
def _append(existing: list, new: list | Any) -> list:
    """Reducer: append new items to the existing list."""
    if existing is None:
        existing = []
    if isinstance(new, list):
        return existing + new
    return existing + [new]


# ── Agent name type ────────────────────────────────────────────────────────────
AgentName = Literal[
    "supervisor",
    "resume_agent",
    "skill_gap_agent",
    "career_agent",
    "interview_agent",
    "rag_agent",
    "END",
]


# ── Main state schema ─────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):

    # ── Identity (set once, never mutated) ────────────────────────────────────
    user_id:          int
    session_id:       str       # unique per graph invocation (UUID)
    original_query:   str       # the user's raw input message
    request_id:       str       # trace ID for observability

    # ── Routing (written by supervisor) ───────────────────────────────────────
    next_agent:       AgentName           # which agent to call next
    routing_reason:   str                 # why supervisor chose this agent
    intent:           str                 # classified intent label
    confidence:       float               # routing confidence 0–1
    requires_resume:  bool                # does this request need resume data?
    is_multi_step:    bool                # will multiple agents be chained?

    # ── User context (populated from DB or request) ────────────────────────────
    resume_text:      str | None          # cached resume raw text
    user_skills:      list[str]           # extracted skills
    user_interests:   list[str]           # user interests
    years_experience: float
    education_level:  str
    target_role:      str | None
    target_company:   str | None

    # ── Conversation memory (append-only accumulator) ─────────────────────────
    messages: Annotated[list[dict], _append]
    # Each message: {"role": "user"|"assistant"|"tool", "content": "...", "agent": "...", "ts": "..."}

    # ── Agent outputs (each agent writes to its own namespace) ─────────────────
    resume_output:    dict | None         # from resume_agent
    skill_gap_output: dict | None         # from skill_gap_agent
    career_output:    dict | None         # from career_agent
    interview_output: dict | None         # from interview_agent
    rag_output:       dict | None         # from rag_agent

    # ── Final response (assembled by response_builder node) ───────────────────
    final_response:   str                 # human-readable answer
    citations:        list[dict]          # source citations from RAG
    suggested_actions: list[dict]         # follow-up action suggestions

    # ── Graph control ──────────────────────────────────────────────────────────
    iteration:        int                 # number of agent hops so far
    max_iterations:   int                 # safety ceiling (default 5)
    agent_chain:      list[str]           # ordered list of agents visited

    # ── Error handling ─────────────────────────────────────────────────────────
    error:            str | None          # error message if a node fails
    error_agent:      str | None          # which agent raised the error
    has_error:        bool

    # ── Metadata ──────────────────────────────────────────────────────────────
    total_tokens:     int                 # accumulated token count
    total_latency_ms: int                 # accumulated processing time


# ── Initial state factory ─────────────────────────────────────────────────────
def initial_state(
    user_id:       int,
    query:         str,
    session_id:    str,
    request_id:    str = "",
    resume_text:   str | None = None,
    user_skills:   list[str] = None,
    user_interests: list[str] = None,
    years_experience: float = 0.0,
    education_level: str = "Bachelors",
    target_role:   str | None = None,
    target_company: str | None = None,
) -> AgentState:
    """Create a fresh AgentState for a new graph invocation."""
    return AgentState(
        user_id=user_id,
        session_id=session_id,
        original_query=query,
        request_id=request_id,
        next_agent="supervisor",
        routing_reason="",
        intent="",
        confidence=0.0,
        requires_resume=False,
        is_multi_step=False,
        resume_text=resume_text,
        user_skills=user_skills or [],
        user_interests=user_interests or [],
        years_experience=years_experience,
        education_level=education_level,
        target_role=target_role,
        target_company=target_company,
        messages=[{"role": "user", "content": query, "agent": "user"}],
        resume_output=None,
        skill_gap_output=None,
        career_output=None,
        interview_output=None,
        rag_output=None,
        final_response="",
        citations=[],
        suggested_actions=[],
        iteration=0,
        max_iterations=5,
        agent_chain=[],
        error=None,
        error_agent=None,
        has_error=False,
        total_tokens=0,
        total_latency_ms=0,
    )
