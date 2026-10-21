"""
app/langgraph/graph.py
───────────────────────
LangGraph workflow — assembles, compiles and runs the multi-agent graph.

Graph topology:

  ┌─────────────────────────────────────────────────────────┐
  │                     START                               │
  └──────────────────────┬──────────────────────────────────┘
                         │
                   [supervisor]
                         │
          ┌──────────────┼──────────────────────┐
          ↓              ↓              ↓        ↓        ↓
    [resume_agent] [skill_gap] [career] [interview] [rag_agent]
          └──────────────┼──────────────────────┘
                         │
                [response_builder]
                         │
                       [END]

Error path: any node → [error_handler] → [END]

The graph is compiled once at module import and cached.
Each invocation gets its own AgentState instance.
"""
from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph  # type: ignore[import]

from app.core.logging import get_logger
from app.langgraph.nodes.agent_nodes import (
    career_node,
    error_handler_node,
    interview_node,
    rag_node,
    response_builder_node,
    resume_node,
    skill_gap_node,
)
from app.langgraph.nodes.supervisor import route_after_supervisor, supervisor_node
from app.langgraph.state import AgentState, initial_state

logger = get_logger(__name__)


# ── Conditional edge: route to error handler if has_error ────────────────────
def _route_after_agent(state: AgentState) -> str:
    if state.get("has_error"):
        return "error_handler"
    return "response_builder"


# ── Graph builder ─────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def build_graph():
    """
    Build and compile the LangGraph StateGraph.
    Cached — only compiled once per process.
    """
    workflow = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────────────────────
    workflow.add_node("supervisor",       supervisor_node)
    workflow.add_node("resume_agent",     resume_node)
    workflow.add_node("skill_gap_agent",  skill_gap_node)
    workflow.add_node("career_agent",     career_node)
    workflow.add_node("interview_agent",  interview_node)
    workflow.add_node("rag_agent",        rag_node)
    workflow.add_node("response_builder", response_builder_node)
    workflow.add_node("error_handler",    error_handler_node)

    # ── Entry point ────────────────────────────────────────────────────────────
    workflow.add_edge(START, "supervisor")

    # ── Supervisor → specialist agent (conditional routing) ───────────────────
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "resume_agent":    "resume_agent",
            "skill_gap_agent": "skill_gap_agent",
            "career_agent":    "career_agent",
            "interview_agent": "interview_agent",
            "rag_agent":       "rag_agent",
            "END":             END,
        },
    )

    # ── Each specialist → response_builder OR error_handler ───────────────────
    for agent in ("resume_agent", "skill_gap_agent", "career_agent",
                  "interview_agent", "rag_agent"):
        workflow.add_conditional_edges(
            agent,
            _route_after_agent,
            {
                "response_builder": "response_builder",
                "error_handler":    "error_handler",
            },
        )

    # ── Terminal edges ─────────────────────────────────────────────────────────
    workflow.add_edge("response_builder", END)
    workflow.add_edge("error_handler",    END)

    compiled = workflow.compile()
    logger.info("langgraph_compiled", nodes=list(workflow.nodes))
    return compiled


# ── Public runner ──────────────────────────────────────────────────────────────
def run_graph(
    user_id:          int,
    query:            str,
    session_id:       str | None    = None,
    resume_text:      str | None    = None,
    user_skills:      list[str]     = None,
    user_interests:   list[str]     = None,
    years_experience: float         = 0.0,
    education_level:  str           = "Bachelors",
    target_role:      str | None    = None,
    target_company:   str | None    = None,
    prior_messages:   list[dict]    = None,
) -> dict[str, Any]:
    """
    Execute the multi-agent graph for a single user query.

    Args:
        user_id:          Authenticated user ID
        query:            User's natural language query
        session_id:       Conversation session ID (generated if None)
        resume_text:      Cached resume raw text (loaded from DB by caller)
        user_skills:      Pre-extracted skill list
        user_interests:   User's stated interests
        years_experience: Years of professional experience
        education_level:  Highest degree
        target_role:      Target job role (if known)
        target_company:   Target company (if known)
        prior_messages:   Previous conversation turns for multi-turn context

    Returns:
        Dict with: final_response, citations, suggested_actions,
                   agent_chain, intent, routing_reason, total_tokens,
                   total_latency_ms, session_id, has_error, error
    """
    sid   = session_id or str(uuid.uuid4())
    state = initial_state(
        user_id=user_id,
        query=query,
        session_id=sid,
        request_id=str(uuid.uuid4()),
        resume_text=resume_text,
        user_skills=user_skills or [],
        user_interests=user_interests or [],
        years_experience=years_experience,
        education_level=education_level,
        target_role=target_role,
        target_company=target_company,
    )

    # Inject prior conversation turns for multi-turn continuity
    if prior_messages:
        state["messages"] = prior_messages + state["messages"]

    graph   = build_graph()
    logger.info("graph_run_start", session=sid, user=user_id, query_preview=query[:60])

    try:
        final_state: AgentState = graph.invoke(state)
    except Exception as exc:
        logger.error("graph_invoke_failed", error=str(exc), session=sid)
        return {
            "session_id":       sid,
            "final_response":   f"I encountered an unexpected error: {exc}",
            "citations":        [],
            "suggested_actions": [],
            "agent_chain":      [],
            "intent":           "error",
            "routing_reason":   "",
            "total_tokens":     0,
            "total_latency_ms": 0,
            "has_error":        True,
            "error":            str(exc),
        }

    logger.info(
        "graph_run_complete",
        session=sid,
        chain=final_state.get("agent_chain"),
        latency=final_state.get("total_latency_ms"),
        tokens=final_state.get("total_tokens"),
    )

    return {
        "session_id":        sid,
        "final_response":    final_state.get("final_response") or "",
        "citations":         final_state.get("citations") or [],
        "suggested_actions": final_state.get("suggested_actions") or [],
        "agent_chain":       final_state.get("agent_chain") or [],
        "intent":            final_state.get("intent") or "",
        "routing_reason":    final_state.get("routing_reason") or "",
        "confidence":        final_state.get("confidence") or 0.0,
        "total_tokens":      final_state.get("total_tokens") or 0,
        "total_latency_ms":  final_state.get("total_latency_ms") or 0,
        "has_error":         final_state.get("has_error") or False,
        "error":             final_state.get("error"),
        # Agent outputs for UI inspection
        "resume_output":     final_state.get("resume_output"),
        "skill_gap_output":  final_state.get("skill_gap_output"),
        "career_output":     final_state.get("career_output"),
        "interview_output":  final_state.get("interview_output"),
        "rag_output":        final_state.get("rag_output"),
        # Messages for conversation history
        "messages":          final_state.get("messages") or [],
    }
