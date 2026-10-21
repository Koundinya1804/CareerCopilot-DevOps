"""
app/langgraph/nodes/agent_nodes.py
────────────────────────────────────
Specialist agent nodes for the LangGraph workflow.

Each node is a pure function:  AgentState → AgentState (partial update)

Nodes call the existing service/agent code — they are thin adapters
that translate the graph state into service calls and write results back.

Nodes:
  resume_node()      → calls resume analysis pipeline
  skill_gap_node()   → calls skill gap agent
  career_node()      → calls career recommendation engine
  interview_node()   → generates interview questions or evaluates answers
  rag_node()         → calls RAG chain for knowledge Q&A
  response_builder() → assembles the final human-readable response
  error_handler()    → formats errors into a friendly response
"""
from __future__ import annotations

import time
from datetime import datetime, UTC

from app.core.config import settings
from app.core.logging import get_logger
from app.langgraph.state import AgentState

logger = get_logger(__name__)


# ── Helper: safe state merge ───────────────────────────────────────────────────
def _update(state: AgentState, **kwargs) -> AgentState:
    """Return a new state dict with the given fields updated."""
    new = dict(state)
    new.update(kwargs)
    return AgentState(**new)  # type: ignore[return-value]


def _append_message(state: AgentState, content: str, agent: str) -> list[dict]:
    existing = list(state.get("messages") or [])
    existing.append({
        "role":    "assistant",
        "content": content,
        "agent":   agent,
        "ts":      datetime.now(UTC).isoformat(),
    })
    return existing


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 1 — Resume Agent
# ═══════════════════════════════════════════════════════════════════════════════
def resume_node(state: AgentState) -> AgentState:
    """
    Runs resume analysis on the cached resume text.
    Populates: resume_output, user_skills (extracted from resume).
    """
    t0 = time.monotonic()
    logger.info("resume_node_start", session=state.get("session_id"))

    resume_text = state.get("resume_text") or ""
    if not resume_text or len(resume_text.strip()) < 50:
        return _update(
            state,
            resume_output={"error": "No resume text available. Please upload and analyse your resume first."},
            agent_chain=(state.get("agent_chain") or []) + ["resume_agent"],
            final_response="I need your resume text to perform this analysis. Please upload your resume via the /resume/upload-and-analyse endpoint first.",
            messages=_append_message(state, "Resume text not available.", "resume_agent"),
        )

    try:
        from app.utils.nlp_extractor import extract_entities
        from app.utils.pdf_parser import _detect_sections
        from app.utils.ats_scorer import calculate_ats_score

        # NLP extraction
        sections  = _detect_sections(resume_text)
        entities  = extract_entities(resume_text, sections)
        ats       = calculate_ats_score(
            resume_text, entities, sections,
            len(resume_text.split()), 1,
            target_role=state.get("target_role"),
        )

        skills    = [s["name"] for s in entities.skills]
        output    = {
            "ats_score":       ats.ats_score,
            "grade":           ats.grade,
            "verdict":         ats.verdict,
            "skills_found":    skills,
            "keywords_found":  ats.keywords_found,
            "keywords_missing": ats.keywords_missing,
            "seniority":       entities.detected_seniority,
            "years_exp":       entities.total_years_exp,
            "education_level": entities.education_level,
        }
        elapsed = int((time.monotonic() - t0) * 1000)
        response = (
            f"**Resume Analysis Complete** 📄\n\n"
            f"**ATS Score:** {ats.ats_score:.1f}/100 (Grade {ats.grade})\n"
            f"**Verdict:** {ats.verdict}\n"
            f"**Skills Found ({len(skills)}):** {', '.join(skills[:10])}\n"
            f"**Experience Level:** {entities.detected_seniority}\n"
            f"**Missing Keywords:** {', '.join(ats.keywords_missing[:5]) or 'None detected'}"
        )
        return _update(
            state,
            resume_output=output,
            user_skills=skills,
            years_experience=entities.total_years_exp,
            education_level=entities.education_level,
            final_response=response,
            agent_chain=(state.get("agent_chain") or []) + ["resume_agent"],
            messages=_append_message(state, response, "resume_agent"),
            total_latency_ms=(state.get("total_latency_ms") or 0) + elapsed,
        )

    except Exception as exc:
        logger.error("resume_node_error", error=str(exc))
        return _update(
            state,
            has_error=True,
            error=str(exc),
            error_agent="resume_agent",
            agent_chain=(state.get("agent_chain") or []) + ["resume_agent"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 2 — Skill Gap Agent
# ═══════════════════════════════════════════════════════════════════════════════
def skill_gap_node(state: AgentState) -> AgentState:
    """
    Runs skill gap analysis for the target role against user's skills.
    Populates: skill_gap_output.
    """
    t0 = time.monotonic()
    logger.info("skill_gap_node_start", session=state.get("session_id"))

    skills      = state.get("user_skills") or []
    target_role = state.get("target_role")
    resume_text = state.get("resume_text") or ""

    if not skills and not resume_text:
        return _update(
            state,
            skill_gap_output={"error": "No skills available. Please analyse your resume first."},
            final_response="I need your skills to perform a gap analysis. Please share your resume or list your skills.",
            agent_chain=(state.get("agent_chain") or []) + ["skill_gap_agent"],
            messages=_append_message(state, "No skills data available.", "skill_gap_agent"),
        )

    if not target_role:
        # Extract target role from query
        query = state.get("original_query", "")
        import re
        m = re.search(
            r"(?:for|as|become|to be|role of)\s+(?:a\s+|an\s+)?([A-Za-z\s]+(?:engineer|developer|scientist|analyst|manager|architect))",
            query, re.IGNORECASE
        )
        target_role = m.group(1).strip() if m else "Software Engineer"

    try:
        from app.agents.skill_gap_agent import run_skill_gap_analysis
        result = run_skill_gap_analysis(
            resume_text=resume_text,
            role_key=_map_to_role_key(target_role),
            target_company=state.get("target_company"),
            extra_skills=skills,
        )

        output = {
            "overall_match_pct":   result.overall_match_pct,
            "required_match_pct":  result.required_match_pct,
            "gap_severity":        result.gap_severity,
            "missing_required":    result.missing_required[:8],
            "matched_skills":      result.matched_skills[:10],
            "learning_priorities": result.learning_priorities[:5],
            "recommended_courses": result.recommended_courses[:3],
            "estimated_prep_months": result.estimated_prep_months,
            "executive_summary":   result.executive_summary,
        }

        elapsed  = int((time.monotonic() - t0) * 1000)
        missing_names = [s.get("name", "") for s in result.missing_required[:5]]
        response = (
            f"**Skill Gap Analysis** 📊\n\n"
            f"**Role:** {result.role_title}\n"
            f"**Overall Match:** {result.overall_match_pct:.1f}%\n"
            f"**Required Skills Match:** {result.required_match_pct:.1f}%\n"
            f"**Gap Severity:** {result.gap_severity.title()}\n"
            f"**Estimated Prep Time:** {result.estimated_prep_months} months\n\n"
            f"**Top Missing Skills:** {', '.join(missing_names) or 'None'}\n\n"
            + (f"**Summary:** {result.executive_summary}" if result.executive_summary else "")
        )

        return _update(
            state,
            skill_gap_output=output,
            target_role=result.role_title,
            final_response=response,
            agent_chain=(state.get("agent_chain") or []) + ["skill_gap_agent"],
            messages=_append_message(state, response, "skill_gap_agent"),
            total_latency_ms=(state.get("total_latency_ms") or 0) + elapsed,
            total_tokens=(state.get("total_tokens") or 0) + result.tokens_consumed,
        )

    except Exception as exc:
        logger.error("skill_gap_node_error", error=str(exc))
        return _update(
            state,
            has_error=True,
            error=str(exc),
            error_agent="skill_gap_agent",
            agent_chain=(state.get("agent_chain") or []) + ["skill_gap_agent"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 3 — Career Recommendation Agent
# ═══════════════════════════════════════════════════════════════════════════════
def career_node(state: AgentState) -> AgentState:
    """
    Generates career role recommendations based on skills and interests.
    Populates: career_output.
    """
    t0 = time.monotonic()
    logger.info("career_node_start", session=state.get("session_id"))

    skills      = state.get("user_skills") or []
    interests   = state.get("user_interests") or []
    resume_text = state.get("resume_text") or ""

    if not skills and not resume_text:
        return _update(
            state,
            career_output={"error": "No profile data available."},
            final_response="Please share your skills or upload your resume so I can recommend career paths for you.",
            agent_chain=(state.get("agent_chain") or []) + ["career_agent"],
            messages=_append_message(state, "No profile data.", "career_agent"),
        )

    try:
        from app.agents.career_recommendation_agent import run_career_recommendation
        result = run_career_recommendation(
            resume_text=resume_text,
            skills=skills,
            interests=interests,
            years_experience=state.get("years_experience") or 0.0,
            education_level=state.get("education_level") or "Bachelors",
        )

        top_roles = result.recommended_roles[:3]
        output    = {
            "top_roles":         [
                {
                    "rank":            r.rank,
                    "role_title":      r.role_title,
                    "domain":          r.domain,
                    "suitability":     r.suitability_score,
                    "suitability_label": r.suitability_label,
                    "salary_journey":  r.salary_journey,
                    "skill_gaps":      r.skill_gaps,
                }
                for r in top_roles
            ],
            "best_domain":       result.best_domain,
            "career_narrative":  result.career_narrative,
            "action_plan":       result.action_plan,
        }

        elapsed  = int((time.monotonic() - t0) * 1000)
        roles_text = "\n".join(
            f"  {r.rank}. **{r.role_title}** ({r.domain}) — {r.suitability_score:.0f}% match"
            for r in top_roles
        )
        response = (
            f"**Career Recommendations** 🎯\n\n"
            f"**Your Best Fit Domain:** {result.best_domain}\n\n"
            f"**Top Recommended Roles:**\n{roles_text}\n\n"
            + (f"**Career Narrative:** {result.career_narrative}" if result.career_narrative else "")
        )

        return _update(
            state,
            career_output=output,
            final_response=response,
            agent_chain=(state.get("agent_chain") or []) + ["career_agent"],
            messages=_append_message(state, response, "career_agent"),
            total_latency_ms=(state.get("total_latency_ms") or 0) + elapsed,
            total_tokens=(state.get("total_tokens") or 0) + result.tokens_consumed,
        )

    except Exception as exc:
        logger.error("career_node_error", error=str(exc))
        return _update(
            state,
            has_error=True,
            error=str(exc),
            error_agent="career_agent",
            agent_chain=(state.get("agent_chain") or []) + ["career_agent"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 4 — Interview Agent
# ═══════════════════════════════════════════════════════════════════════════════
def interview_node(state: AgentState) -> AgentState:
    """
    Generates interview questions or evaluates an answer from the query.
    Populates: interview_output.
    """
    t0    = time.monotonic()
    query = state.get("original_query", "").lower()
    logger.info("interview_node_start", session=state.get("session_id"))

    # Detect sub-intent: generate questions vs evaluate an answer
    is_evaluate = any(w in query for w in ("my answer", "evaluate", "how did i do", "assess my"))
    mode = "technical" if any(w in query for w in ("technical", "coding", "system design", "algorithm")) else "hr"
    if state.get("target_company"):
        mode = "company_specific"

    try:
        from app.agents.interview_coach_agent import generate_questions, evaluate_answer_with_ai

        if is_evaluate:
            # Try to find an answer in the query after "my answer:" or similar
            import re
            m = re.search(r"(?:my answer[:\s]+|answer[:\s]+)(.*)", state.get("original_query", ""), re.IGNORECASE | re.DOTALL)
            answer_text = m.group(1).strip() if m else state.get("original_query", "")
            q_text      = "Evaluate my interview answer"

            feedback = evaluate_answer_with_ai(
                question=q_text,
                answer=answer_text,
                question_type="behavioural",
                target_role=state.get("target_role"),
            )
            output = {
                "type":          "evaluation",
                "scores":        {
                    "overall":       feedback.scores.overall_score,
                    "confidence":    feedback.scores.confidence_score,
                    "technical":     feedback.scores.technical_score,
                    "communication": feedback.scores.communication_score,
                },
                "model_answer":   feedback.model_answer,
                "qualitative":    feedback.qualitative,
            }
            elapsed  = int((time.monotonic() - t0) * 1000)
            response = (
                f"**Answer Evaluation** 🎯\n\n"
                f"**Overall Score:** {feedback.scores.overall_score:.1f}/100\n"
                f"**Confidence:** {feedback.scores.confidence_score:.1f} | "
                f"**Communication:** {feedback.scores.communication_score:.1f}\n\n"
                f"**Model Answer:**\n{feedback.model_answer}"
            )
        else:
            # Generate questions
            questions = generate_questions(
                mode=mode,
                n=3,
                target_role=state.get("target_role") or "Software Engineer",
                target_company=state.get("target_company"),
                difficulty="medium",
                resume_text=state.get("resume_text") or "",
            )
            output   = {
                "type":      "questions",
                "mode":      mode,
                "questions": [
                    {
                        "number":        i + 1,
                        "question":      q.question_text,
                        "type":          q.question_type,
                        "follow_up":     q.follow_up_hint,
                    }
                    for i, q in enumerate(questions)
                ],
            }
            elapsed  = int((time.monotonic() - t0) * 1000)
            qs_text  = "\n\n".join(
                f"**Q{i+1}** [{q.question_type.upper()}]\n{q.question_text}\n*Follow-up: {q.follow_up_hint}*"
                for i, q in enumerate(questions)
            )
            company_ctx = f" for {state.get('target_company')}" if state.get("target_company") else ""
            response = (
                f"**Interview Questions{company_ctx}** 🎤\n\n"
                f"Mode: {mode.replace('_', ' ').title()} | "
                f"Role: {state.get('target_role') or 'Software Engineer'}\n\n"
                + qs_text
            )

        return _update(
            state,
            interview_output=output,
            final_response=response,
            agent_chain=(state.get("agent_chain") or []) + ["interview_agent"],
            messages=_append_message(state, response, "interview_agent"),
            total_latency_ms=(state.get("total_latency_ms") or 0) + elapsed,
        )

    except Exception as exc:
        logger.error("interview_node_error", error=str(exc))
        return _update(
            state,
            has_error=True,
            error=str(exc),
            error_agent="interview_agent",
            agent_chain=(state.get("agent_chain") or []) + ["interview_agent"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 5 — RAG Agent
# ═══════════════════════════════════════════════════════════════════════════════
def rag_node(state: AgentState) -> AgentState:
    """
    Answers general knowledge queries using the RAG pipeline.
    Populates: rag_output, citations.
    """
    t0 = time.monotonic()
    logger.info("rag_node_start", session=state.get("session_id"))

    query       = state.get("original_query", "")
    # Build conversation history for multi-turn context
    history     = [
        m for m in (state.get("messages") or [])
        if m.get("role") in ("user", "assistant") and m != (state.get("messages") or [])[-1]
    ]

    try:
        from app.rag.chains.rag_chain import get_rag_chain
        result = get_rag_chain(
            query=query,
            chat_history=history[-6:],  # last 6 turns for context
        )

        output  = {
            "answer":      result.answer,
            "citations":   result.citations,
            "chunks_used": result.chunks_used,
            "categories":  result.categories,
            "has_answer":  result.has_answer,
            "answered_from_kb": result.answered_from_kb,
        }
        elapsed = int((time.monotonic() - t0) * 1000)

        return _update(
            state,
            rag_output=output,
            final_response=result.answer,
            citations=result.citations,
            agent_chain=(state.get("agent_chain") or []) + ["rag_agent"],
            messages=_append_message(state, result.answer, "rag_agent"),
            total_latency_ms=(state.get("total_latency_ms") or 0) + elapsed,
            total_tokens=(state.get("total_tokens") or 0) + result.tokens_used,
        )

    except Exception as exc:
        logger.error("rag_node_error", error=str(exc))
        return _update(
            state,
            has_error=True,
            error=str(exc),
            error_agent="rag_agent",
            agent_chain=(state.get("agent_chain") or []) + ["rag_agent"],
        )


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 6 — Response Builder
# ═══════════════════════════════════════════════════════════════════════════════
def response_builder_node(state: AgentState) -> AgentState:
    """
    Assembles the final response if multiple agents ran.
    Also generates suggested follow-up actions.
    """
    # If a single agent ran and set final_response, just enrich it
    response = state.get("final_response") or ""

    # Build follow-up suggestions based on what agents ran
    chain     = state.get("agent_chain") or []
    actions   = _suggest_actions(state, chain)

    return _update(
        state,
        final_response=response,
        suggested_actions=actions,
    )


def _suggest_actions(state: AgentState, chain: list[str]) -> list[dict]:
    """Generate context-aware next-step suggestions."""
    actions = []
    agents_run = set(chain)

    if "resume_agent" in agents_run and "skill_gap_agent" not in agents_run:
        actions.append({"action": "skill_gap", "label": "Analyse your skill gap",
                        "description": "See which skills you're missing for your target role"})
    if "career_agent" not in agents_run:
        actions.append({"action": "career_recommend", "label": "Get career recommendations",
                        "description": "Discover which roles you're best suited for"})
    if "interview_agent" not in agents_run:
        actions.append({"action": "start_interview", "label": "Start mock interview",
                        "description": "Practice with AI-powered interview coaching"})
    if "skill_gap_agent" in agents_run:
        actions.append({"action": "view_courses", "label": "View recommended courses",
                        "description": "See curated learning resources to fill your gaps"})

    return actions[:3]


# ═══════════════════════════════════════════════════════════════════════════════
# NODE 7 — Error Handler
# ═══════════════════════════════════════════════════════════════════════════════
def error_handler_node(state: AgentState) -> AgentState:
    """Formats error state into a friendly user-facing response."""
    error       = state.get("error") or "An unexpected error occurred."
    error_agent = state.get("error_agent") or "system"

    logger.error("graph_error_handled", agent=error_agent, error=error,
                 session=state.get("session_id"))

    response = (
        f"I encountered an issue while processing your request.\n\n"
        f"**Error:** {error}\n\n"
        f"Please try rephrasing your query or contact support if this persists."
    )

    return _update(
        state,
        final_response=response,
        messages=_append_message(state, response, "error_handler"),
    )


# ── Utility: map free-text role to role key ────────────────────────────────────
def _map_to_role_key(role_text: str) -> str:
    """Map free-text role description to a known role_key."""
    r = role_text.lower().strip()
    mapping = {
        "ai engineer":          "ai_engineer",
        "ml engineer":          "ml_engineer",
        "machine learning":     "ml_engineer",
        "data scientist":       "data_scientist",
        "data engineer":        "data_engineer",
        "backend":              "backend_engineer",
        "backend engineer":     "backend_engineer",
        "fullstack":            "fullstack_engineer",
        "full stack":           "fullstack_engineer",
        "frontend":             "frontend_engineer",
        "java":                 "java_developer",
        "java developer":       "java_developer",
        "cloud":                "cloud_engineer",
        "cloud engineer":       "cloud_engineer",
        "devops":               "devops_engineer",
        "sre":                  "sre_engineer",
        "mobile":               "mobile_engineer",
        "product manager":      "product_manager",
        "cybersecurity":        "cybersecurity_engineer",
    }
    for key, val in mapping.items():
        if key in r:
            return val
    return "ml_engineer"  # safe default
