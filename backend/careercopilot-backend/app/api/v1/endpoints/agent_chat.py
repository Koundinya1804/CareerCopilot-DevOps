"""
app/api/v1/endpoints/agent_chat.py
────────────────────────────────────
Multi-Agent Supervisor API — single chat interface that routes to all agents:

  POST /api/v1/agent/chat                 — invoke graph, get full response
  POST /api/v1/agent/chat/stream          — SSE streaming response
  GET  /api/v1/agent/sessions/{id}        — get session state & history
  GET  /api/v1/agent/sessions/{id}/messages — full message history
  DELETE /api/v1/agent/sessions/{id}      — clear session memory
  GET  /api/v1/agent/routing-info         — explain routing rules
  POST /api/v1/agent/classify             — classify intent without running agents
"""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, DBSession
from app.core.config import settings
from app.core.logging import get_logger
from app.db.redis import get_redis
from app.db.session import get_db
from app.langgraph.graph import build_graph, run_graph
from app.langgraph.memory.memory_store import GraphMemory
from app.langgraph.nodes.supervisor import _rule_based_route, _detect_multi_step, _detect_resume_required
from app.langgraph.state import initial_state

router = APIRouter(prefix="/agent", tags=["Multi-Agent Supervisor"])
logger = get_logger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query:            str       = Field(..., min_length=3, max_length=3000,
                                        description="Your question or request")
    session_id:       str | None = Field(None, description="Continue existing session")
    resume_text:      str | None = Field(None, max_length=20000,
                                         description="Raw resume text (optional)")
    user_skills:      list[str] = Field(default_factory=list)
    user_interests:   list[str] = Field(default_factory=list)
    years_experience: float     = Field(0.0, ge=0, le=50)
    education_level:  str       = Field("Bachelors")
    target_role:      str | None = None
    target_company:   str | None = None
    include_history:  bool       = Field(True, description="Include prior session messages")


class ClassifyRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000)


class APIResponse(BaseModel):
    success: bool = True
    message: str  = "OK"
    data:    Any  = None


# ── Helper: load session context from memory ──────────────────────────────────
def _load_session_context(
    session_id: str | None,
    user_id: int,
    redis: Redis,  # type: ignore[type-arg]
) -> dict:
    """Load cached context from Redis for session continuity."""
    memory = GraphMemory(redis)
    ctx    = {}

    if session_id:
        state = memory.load_state(session_id)
        if state:
            ctx["prior_messages"] = memory.load_messages(session_id)
            # Carry forward user context from previous turn
            for field in ("user_skills", "years_experience", "education_level",
                          "target_role", "target_company", "resume_text"):
                if state.get(field):
                    ctx[field] = state[field]

    # Also load long-term user context cache — this is what makes memory
    # persist across brand-new sessions, not just continuations of one.
    user_ctx = memory.load_user_context(user_id)
    if user_ctx:
        for field in ("user_skills", "years_experience", "education_level"):
            if user_ctx.get(field) and not ctx.get(field):
                ctx[field] = user_ctx[field]
        # Career goals / preferences carry forward even into a fresh session
        if not ctx.get("target_role") and user_ctx.get("preferred_role"):
            ctx["target_role"] = user_ctx["preferred_role"]
        if not ctx.get("target_company") and user_ctx.get("preferred_company"):
            ctx["target_company"] = user_ctx["preferred_company"]
        # Surfaced to the caller for display, not fed into graph state directly
        ctx["long_term_memory"] = {
            k: user_ctx.get(k) for k in (
                "career_goal", "career_best_domain", "preferred_role",
                "preferred_company", "resume_improvements", "learning_roadmap",
                "interview_history", "last_ats_score",
            ) if user_ctx.get(k) is not None
        }

    return ctx


def _save_session_result(
    session_id: str,
    user_id:    int,
    result:     dict,
    redis:      Redis,  # type: ignore[type-arg]
) -> None:
    """
    Persist graph result to Redis for next turn, AND roll relevant fields
    into the long-term user context cache (7-day TTL) so they carry across
    brand-new sessions too — not just continuations of the same session_id.

    Long-term memory covers: preferred role/company (career goals), resume
    improvement areas, learning roadmap, and a rolling interview history —
    on top of the skills/education/experience the graph already cached.
    """
    memory = GraphMemory(redis)
    memory.save_state(session_id, result)
    if result.get("messages"):
        memory.append_messages(session_id, result["messages"][-2:])  # last exchange only

    # Track this session for the "recent conversations" list, using the
    # first user message as a preview if this is a new session (don't
    # overwrite an existing preview with a later turn's text).
    is_new_session = not memory.is_session_tracked(user_id, session_id)
    preview = result.get("original_query") if is_new_session else None
    memory.track_user_session(user_id, session_id, preview=preview)

    if result.get("has_error"):
        return

    updates: dict = {}

    # Resume analysis → skills/education/experience (existing) + improvement areas
    if result.get("resume_output") and "error" not in result["resume_output"]:
        ro = result["resume_output"]
        updates.update(
            user_skills=ro.get("skills_found", []),
            education_level=ro.get("education_level"),
            years_experience=ro.get("years_exp"),
            last_ats_score=ro.get("ats_score"),
            resume_improvements=ro.get("keywords_missing", []),
        )

    # Career recommendation → career goal / best-fit domain
    if result.get("career_output") and "error" not in result["career_output"]:
        co = result["career_output"]
        top = (co.get("top_roles") or [None])[0]
        updates.update(
            career_goal=top.get("role_title") if top else co.get("best_domain"),
            career_best_domain=co.get("best_domain"),
        )

    # Skill gap → preferred role + learning roadmap
    if result.get("skill_gap_output") and "error" not in result["skill_gap_output"]:
        sgo = result["skill_gap_output"]
        updates.update(
            preferred_role=result.get("target_role") or sgo.get("role_title"),
            learning_roadmap=sgo.get("learning_priorities", []),
        )

    # Preferred role/company explicitly stated this turn
    if result.get("target_role"):
        updates.setdefault("preferred_role", result["target_role"])
    if result.get("target_company"):
        updates["preferred_company"] = result["target_company"]

    if updates:
        memory.update_user_context(user_id, **updates)

    # Interview evaluations accumulate as a rolling history (last 10), since
    # this is a list that grows over time rather than a value that's replaced.
    io = result.get("interview_output")
    if io and io.get("type") == "evaluation" and "error" not in io:
        existing_ctx = memory.load_user_context(user_id) or {}
        history = list(existing_ctx.get("interview_history") or [])
        history.append({
            "overall_score": io.get("scores", {}).get("overall"),
            "target_role":   result.get("target_role"),
            "session_id":    session_id,
        })
        memory.update_user_context(user_id, interview_history=history[-10:])


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=APIResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with the multi-agent supervisor (synchronous)",
)
def chat(
    req:          ChatRequest,
    current_user: CurrentUser,
    db:           DBSession,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    """
    The main entry point for the CareerCopilot AI multi-agent system.

    The Supervisor Agent automatically:
    1. Classifies your intent from the query
    2. Routes to the best specialist agent
    3. Returns a structured, cited response

    **Example queries:**
    - "Analyse my resume" → Resume Agent
    - "What skills am I missing for ML Engineer?" → Skill Gap Agent
    - "Which career suits me best?" → Career Agent
    - "Start a Google mock interview" → Interview Agent
    - "What is deadlock in OS?" → RAG Agent

    Pass `session_id` from a previous response to continue a multi-turn conversation.
    """
    session_id = req.session_id or str(uuid.uuid4())

    # Load prior context from Redis
    ctx = _load_session_context(session_id, current_user.user_id, redis)

    # Merge request fields with cached context (request takes priority)
    result = run_graph(
        user_id=current_user.user_id,
        query=req.query,
        session_id=session_id,
        resume_text=req.resume_text or ctx.get("resume_text"),
        user_skills=req.user_skills or ctx.get("user_skills", []),
        user_interests=req.user_interests or [],
        years_experience=req.years_experience or ctx.get("years_experience", 0.0),
        education_level=req.education_level or ctx.get("education_level", "Bachelors"),
        target_role=req.target_role or ctx.get("target_role"),
        target_company=req.target_company or ctx.get("target_company"),
        prior_messages=ctx.get("prior_messages", []) if req.include_history else [],
    )

    # Persist result for next turn
    _save_session_result(session_id, current_user.user_id, result, redis)

    logger.info(
        "agent_chat",
        user_id=current_user.user_id,
        session=session_id,
        chain=result.get("agent_chain"),
        intent=result.get("intent"),
        latency=result.get("total_latency_ms"),
    )

    return APIResponse(
        message="Response generated.",
        data={
            "session_id":        result["session_id"],
            "response":          result["final_response"],
            "citations":         result["citations"],
            "suggested_actions": result["suggested_actions"],
            "agent_chain":       result["agent_chain"],
            "intent":            result["intent"],
            "routing_reason":    result["routing_reason"],
            "confidence":        result.get("confidence", 0.0),
            "total_tokens":      result["total_tokens"],
            "total_latency_ms":  result["total_latency_ms"],
            "has_error":         result["has_error"],
            "long_term_memory":  ctx.get("long_term_memory", {}),
            # Structured outputs for advanced UI consumption
            "resume_output":     result.get("resume_output"),
            "skill_gap_output":  result.get("skill_gap_output"),
            "career_output":     result.get("career_output"),
            "interview_output":  result.get("interview_output"),
            "rag_output":        result.get("rag_output"),
        },
    )


@router.post(
    "/chat/stream",
    summary="Chat with streaming SSE response",
    response_class=StreamingResponse,
)
async def chat_stream(
    req:          ChatRequest,
    current_user: CurrentUser,
    db:           DBSession,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> StreamingResponse:
    """
    Streaming version of /chat using Server-Sent Events.
    Emits routing events first, then streams the final response token by token.

    **SSE event types:**
    - `routing`: supervisor decision (instant)
    - `token`: response token
    - `done`: final metadata payload
    - `error`: error event
    """
    session_id = req.session_id or str(uuid.uuid4())
    ctx        = _load_session_context(session_id, current_user.user_id, redis)

    async def event_stream() -> AsyncIterator[str]:
        try:
            # Emit routing event immediately (before heavy computation)
            route_result = _rule_based_route(req.query)
            agent_hint   = route_result[0] if route_result else "rag_agent"
            intent_hint  = route_result[1] if route_result else "general_chat"

            yield f"data: {json.dumps({'type': 'routing', 'agent': agent_hint, 'intent': intent_hint})}\n\n"

            # Run the full graph (blocking — run in threadpool in production)
            result = run_graph(
                user_id=current_user.user_id,
                query=req.query,
                session_id=session_id,
                resume_text=req.resume_text or ctx.get("resume_text"),
                user_skills=req.user_skills or ctx.get("user_skills", []),
                user_interests=req.user_interests or [],
                years_experience=req.years_experience or ctx.get("years_experience", 0.0),
                education_level=req.education_level or ctx.get("education_level", "Bachelors"),
                target_role=req.target_role or ctx.get("target_role"),
                target_company=req.target_company or ctx.get("target_company"),
                prior_messages=ctx.get("prior_messages", []) if req.include_history else [],
            )

            _save_session_result(session_id, current_user.user_id, result, redis)

            # Stream response text word by word
            response_text = result.get("final_response") or ""
            words         = response_text.split(" ")
            chunk_size    = 3  # emit 3 words at a time
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i + chunk_size])
                if chunk:
                    yield f"data: {json.dumps({'type': 'token', 'text': chunk + ' '})}\n\n"

            # Emit final metadata
            yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'agent_chain': result.get('agent_chain', []), 'intent': result.get('intent', ''), 'citations': result.get('citations', []), 'suggested_actions': result.get('suggested_actions', []), 'total_latency_ms': result.get('total_latency_ms', 0)})}\n\n"

        except Exception as exc:
            logger.error("stream_error", error=str(exc))
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/classify",
    response_model=APIResponse,
    summary="Classify a query's intent without running any agents",
)
def classify_intent(
    req:          ClassifyRequest,
    current_user: CurrentUser,
) -> APIResponse:
    """
    Fast intent classification without invoking any agent.
    Useful for real-time UI feedback (show which agent will handle the query).
    """
    route_result = _rule_based_route(req.query)
    if route_result:
        agent, intent, confidence = route_result
        method = "rule_based"
    else:
        agent, intent, confidence = "rag_agent", "general_chat", 0.5
        method = "default"

    return APIResponse(data={
        "query":           req.query,
        "predicted_agent": agent,
        "intent":          intent,
        "confidence":      confidence,
        "method":          method,
        "is_multi_step":   _detect_multi_step(req.query),
        "requires_resume": _detect_resume_required(req.query),
    })


@router.get(
    "/sessions",
    response_model=APIResponse,
    summary="List the current user's recent chat sessions",
)
def list_sessions(
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
    limit:        int   = 20,
) -> APIResponse:
    """
    Powers the chat history sidebar. Sessions are ordered most-recently-
    active first. `still_live` tells the frontend whether a session can
    still be resumed (its own 24h state TTL hasn't expired) or is only
    available as a read-only entry in history (the 7-day history index
    outlives the session state itself).
    """
    sessions = GraphMemory(redis).list_user_sessions(current_user.user_id, limit=limit)
    return APIResponse(data={"sessions": sessions, "total": len(sessions)})


@router.get(
    "/sessions/{session_id}",
    response_model=APIResponse,
    summary="Get session state and metadata",
)
def get_session(
    session_id:   str,
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    memory = GraphMemory(redis)
    state  = memory.load_state(session_id)
    if not state or state.get("user_id") != current_user.user_id:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("AgentSession", session_id)

    return APIResponse(data={
        "session_id":    session_id,
        "agent_chain":   state.get("agent_chain", []),
        "intent":        state.get("intent", ""),
        "has_error":     state.get("has_error", False),
        "total_tokens":  state.get("total_tokens", 0),
        "latency_ms":    state.get("total_latency_ms", 0),
        "ttl_seconds":   memory.get_session_ttl(session_id),
    })


@router.get(
    "/sessions/{session_id}/messages",
    response_model=APIResponse,
    summary="Get full conversation history for a session",
)
def get_session_messages(
    session_id:   str,
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    memory = GraphMemory(redis)
    # Ownership check — a session's state carries the user_id it belongs to.
    # Without this, any authenticated user who obtained/guessed a session_id
    # could read another user's full conversation history.
    state = memory.load_state(session_id)
    if not state or state.get("user_id") != current_user.user_id:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("AgentSession", session_id)

    messages = memory.load_messages(session_id)
    return APIResponse(data={"session_id": session_id, "messages": messages,
                             "total": len(messages)})


@router.delete(
    "/sessions/{session_id}",
    response_model=APIResponse,
    summary="Clear session memory",
)
def delete_session(
    session_id:   str,
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    memory = GraphMemory(redis)
    # Same ownership check as get_session_messages — without it, any
    # authenticated user could delete another user's session by session_id.
    state = memory.load_state(session_id)
    if not state or state.get("user_id") != current_user.user_id:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("AgentSession", session_id)

    memory.delete_session(session_id)
    return APIResponse(message=f"Session {session_id} cleared.")


@router.get(
    "/memory",
    response_model=APIResponse,
    summary="Get the user's long-term memory profile",
)
def get_user_memory(
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    """
    Returns everything the multi-agent system currently remembers about the
    user long-term (persists across sessions, 7-day rolling TTL — refreshed
    on every update): career goal, preferred role/company, resume
    improvement areas, learning roadmap, and recent interview history.
    """
    memory = GraphMemory(redis)
    ctx = memory.load_user_context(current_user.user_id) or {}
    return APIResponse(data={"user_id": current_user.user_id, "memory": ctx})


@router.delete(
    "/memory",
    response_model=APIResponse,
    summary="Clear the user's long-term memory profile",
)
def clear_user_memory(
    current_user: CurrentUser,
    redis:        Redis = Depends(get_redis),  # type: ignore[type-arg]
) -> APIResponse:
    memory = GraphMemory(redis)
    memory.save_user_context(current_user.user_id, {})
    return APIResponse(message="Long-term memory cleared.")


@router.get(
    "/routing-info",
    response_model=APIResponse,
    summary="Get routing rules and supported agents",
)
def routing_info(current_user: CurrentUser) -> APIResponse:
    return APIResponse(data={
        "agents": [
            {"name": "resume_agent",    "triggers": ["analyse resume", "ATS score", "resume feedback"]},
            {"name": "skill_gap_agent", "triggers": ["skill gap", "missing skills", "learning path"]},
            {"name": "career_agent",    "triggers": ["career", "recommend", "best role", "career path"]},
            {"name": "interview_agent", "triggers": ["interview", "mock interview", "interview questions"]},
            {"name": "rag_agent",       "triggers": ["what is", "explain", "how does", "salary", "define"]},
        ],
        "routing_strategy": f"rule_based → {settings.DEFAULT_LLM_PROVIDER}_fallback",
        "multi_turn":        True,
        "memory_backend":    "Redis (TTL 24h)",
        "max_iterations":    5,
    })
