"""
tests/test_supervisor_routing.py
──────────────────────────────────
Dedicated regression suite for the Supervisor's rule-based routing logic
(app/langgraph/nodes/supervisor.py).

This file exists specifically because of a real production bug: salary and
general-knowledge questions were being misrouted to the Knowledge Agent
instead of the Career Agent / general-chat fallback (see CHANGELOG.md,
"Supervisor Routing Audit"). The pre-existing test suite (tests/test_langgraph.py)
had a test that asserted the *buggy* behaviour was correct
(`test_salary_routing_rag`, since renamed/fixed) — this file is the
dedicated home for routing correctness so that class of regression can't
slip back in unnoticed inside a larger, more general test file.

NOTE ON EXECUTION: this file was NOT executed in the sandbox this was
written in — that sandbox has no Python packages installed at all (no
pytest, no structlog, no langgraph), so `app.langgraph.nodes.supervisor`
cannot even be imported there. The routing LOGIC itself (the `_INTENT_MAP`
regex table and the selection algorithm) WAS independently verified by
extracting it directly from the live file and executing it with a bare
Python 3 stdlib script — every case below passed under that verification.
But that is not the same as running this actual pytest file, so treat the
numbers in TEST_REPORT.md accordingly: this suite is production-ready and
believed correct, not proven-by-CI.
"""
from __future__ import annotations

import pytest

from app.langgraph.nodes.supervisor import _rule_based_route, _default_route


# ═════════════════════════════════════════════════════════════════════════════
# Resume Agent
# ═════════════════════════════════════════════════════════════════════════════
class TestResumeAgentRouting:
    @pytest.mark.parametrize("query", [
        "Can you analyse my resume?",
        "Please review my resume",
        "What's my ATS score?",
        "Check my resume for issues",
        "Give me resume feedback",
    ])
    def test_routes_to_resume_agent(self, query):
        result = _rule_based_route(query)
        assert result is not None
        assert result[0] == "resume_agent"
        assert result[2] >= 0.8  # high-confidence match expected


# ═════════════════════════════════════════════════════════════════════════════
# Skill Gap Agent
# ═════════════════════════════════════════════════════════════════════════════
class TestSkillGapAgentRouting:
    @pytest.mark.parametrize("query", [
        "What skill gap do I have for ML Engineer?",
        "What skills am I missing for a Data Scientist role?",
        "What skills are needed for backend development?",
        "I want to know my skill match for DevOps",
        "Suggest a learning path for cloud engineering",
    ])
    def test_routes_to_skill_gap_agent(self, query):
        result = _rule_based_route(query)
        assert result is not None
        assert result[0] == "skill_gap_agent"


# ═════════════════════════════════════════════════════════════════════════════
# Career Agent — advice, roles, salary, placements, companies, internships, roadmaps
# ═════════════════════════════════════════════════════════════════════════════
class TestCareerAgentRouting:
    @pytest.mark.parametrize("query", [
        "What career should I pursue?",
        "What career suits someone with Python and SQL skills?",
        "Which role is best for me?",
        "Give me a career roadmap for backend development",
        "What companies are hiring for internships?",
        "What is the placement package at TCS?",
        "How is the salary for trainee SDE at Google?",   # original bug report #1
        "What is the average pay for a data analyst?",
        "What is the CTC offered by Amazon for freshers?",
    ])
    def test_routes_to_career_agent(self, query):
        result = _rule_based_route(query)
        assert result is not None
        assert result[0] == "career_agent"

    def test_salary_no_longer_routes_to_knowledge_agent(self):
        """Regression test for the exact bug reported in production."""
        result = _rule_based_route("How is the salary for trainee SDE at Google?")
        assert result is not None
        assert result[0] == "career_agent", (
            "Salary questions must route to Career Agent, not Knowledge Agent "
            "(rag_agent) — this was the original production bug."
        )

    def test_career_question_mentioning_tech_name_still_career(self):
        """A career-fit question that happens to mention a language/tool
        name must NOT be hijacked into Knowledge Agent just because the
        tech name appears in the sentence."""
        result = _rule_based_route("What career suits someone with Python and SQL skills?")
        assert result is not None
        assert result[0] == "career_agent"


# ═════════════════════════════════════════════════════════════════════════════
# Interview Agent — mock interviews, company-specific prep
# ═════════════════════════════════════════════════════════════════════════════
class TestInterviewAgentRouting:
    @pytest.mark.parametrize("query", [
        "Give me mock interview questions",
        "Can you conduct a mock interview?",
        "Help me prepare for an interview",
        "What are common interview tips?",
    ])
    def test_routes_to_interview_agent(self, query):
        result = _rule_based_route(query)
        assert result is not None
        assert result[0] == "interview_agent"

    @pytest.mark.parametrize("query", [
        "What is Google's interview process like?",
        "How to prepare for Amazon interview rounds",
        "Tell me about Microsoft's hiring process",
        "What does the TCS interview round look like?",
    ])
    def test_company_interview_questions_route_to_interview_agent(self, query):
        """Company name + interview/process/round context must win over the
        more generic Career Agent rule."""
        result = _rule_based_route(query)
        assert result is not None
        assert result[0] == "interview_agent"


# ═════════════════════════════════════════════════════════════════════════════
# Knowledge Agent (RAG) — CS concepts, programming, DSA, uploaded docs
# ═════════════════════════════════════════════════════════════════════════════
class TestKnowledgeAgentRouting:
    @pytest.mark.parametrize("query", [
        "What is the difference between TCP and UDP?",
        "Explain deadlock in operating systems",
        "Tell me about DBMS normalization",
        "Explain OOP concepts",
        "What is a linked list?",
        "Explain recursion with an example",
        "What is inheritance in Java?",
        "Explain the difference between SQL and NoSQL databases",
    ])
    def test_routes_to_knowledge_agent(self, query):
        result = _rule_based_route(query)
        assert result is not None
        assert result[0] == "rag_agent"

    def test_document_search_routes_to_knowledge_agent(self):
        result = _rule_based_route("Search my uploaded documents for this topic")
        assert result is not None
        assert result[0] == "rag_agent"


# ═════════════════════════════════════════════════════════════════════════════
# General Chat fallback — no rule matches at all
# ═════════════════════════════════════════════════════════════════════════════
class TestGeneralChatFallback:
    @pytest.mark.parametrize("query", [
        "Who is Sundar Pichai?",              # original bug report #2
        "Who is the CEO of Microsoft?",
        "Tell me a joke",
        "What's the weather like today?",
    ])
    def test_unmatched_queries_return_none_from_rule_router(self, query):
        """These queries must match no keyword rule at all — the general-
        chat behaviour comes from _default_route(), not from a rule."""
        result = _rule_based_route(query)
        assert result is None

    def test_generic_what_is_phrasing_still_lands_on_knowledge_agent(self):
        """'What is the capital of France?' DOES match the low-confidence
        generic 'what is / explain' catch-all rule (by design — that rule
        exists to catch broadly-phrased knowledge questions). This is fine:
        it still correctly resolves to rag_agent, just via the rule path
        instead of the _default_route fallback path. Both paths lead to the
        same place; this test documents that the catch-all matching a
        general-knowledge question is expected, not a bug — the fallback
        prompt in rag_chain.py is what actually makes the final answer
        correct for a query the KB has no coverage for."""
        result = _rule_based_route("What is the capital of France?")
        assert result is not None
        assert result[0] == "rag_agent"

    @pytest.mark.parametrize("query", [
        "Who is Sundar Pichai?",
        "Tell me a joke",
        "What's the weather like today?",
    ])
    def test_default_route_lands_on_rag_agent_as_general_chat(self, query):
        """There is no separate 'general LLM' node in the graph — rag_agent
        IS the general-LLM handler once ChromaDB retrieval comes back empty
        (see app/rag/chains/rag_chain.py's fallback prompt). _default_route
        is what supervisor_node calls when _rule_based_route returns None."""
        agent, intent, confidence = _default_route(query)
        assert agent == "rag_agent"
        assert intent == "general_chat"
        assert 0.0 < confidence <= 1.0

    def test_who_is_sundar_pichai_full_fallback_chain(self):
        """End-to-end regression test for bug report #2: an unmatched
        general-knowledge question about a person must end up routed to
        rag_agent with intent general_chat, not silently defaulting to a
        broken/dead classifier."""
        rule_result = _rule_based_route("Who is Sundar Pichai?")
        assert rule_result is None
        agent, intent, _ = _default_route("Who is Sundar Pichai?")
        assert agent == "rag_agent"
        assert intent == "general_chat"


# ═════════════════════════════════════════════════════════════════════════════
# Unknown / nonsense queries
# ═════════════════════════════════════════════════════════════════════════════
class TestUnknownQueries:
    @pytest.mark.parametrize("query", [
        "xyzzy quux blergh",
        "asdkjfh alksjdf laksjdf",
        "!!!???...",
        "12345 67890",
    ])
    def test_nonsense_query_matches_no_rule(self, query):
        result = _rule_based_route(query)
        assert result is None

    def test_nonsense_query_still_gets_a_safe_default(self):
        """Even total nonsense must resolve to *some* agent — never None or
        a crash — since supervisor_node always calls _default_route as the
        fallback."""
        agent, intent, confidence = _default_route("xyzzy quux blergh")
        assert agent == "rag_agent"
        assert intent == "general_chat"


# ═════════════════════════════════════════════════════════════════════════════
# Empty / degenerate prompts
# ═════════════════════════════════════════════════════════════════════════════
class TestEmptyPrompts:
    def test_empty_string_does_not_crash(self):
        result = _rule_based_route("")
        assert result is None

    def test_whitespace_only_does_not_crash(self):
        result = _rule_based_route("   \n\t  ")
        assert result is None

    def test_default_route_handles_empty_string(self):
        agent, intent, confidence = _default_route("")
        assert agent == "rag_agent"
        assert intent == "general_chat"

    def test_none_like_falsy_query_does_not_raise(self):
        # _rule_based_route always receives a str from the API layer
        # (Pydantic validates the request body), but it should not blow up
        # on an empty string in particular since that's easy to reach via
        # a client bug or a stripped-whitespace input.
        try:
            result = _rule_based_route("")
        except Exception as exc:  # pragma: no cover - should never happen
            pytest.fail(f"_rule_based_route('') raised unexpectedly: {exc}")
        assert result is None


# ═════════════════════════════════════════════════════════════════════════════
# Regression tests for previously-fixed bugs
# ═════════════════════════════════════════════════════════════════════════════
class TestRoutingRegressions:
    """
    One test per confirmed production bug from the routing audit. Keep this
    class growing over time — every future routing bug report should land
    a new test here before the fix, not just a fix to _INTENT_MAP.
    """

    def test_bug_1_salary_question_routes_to_career_not_knowledge(self):
        result = _rule_based_route("How is the salary for trainee SDE at Google?")
        assert result is not None
        assert result[0] == "career_agent"

    def test_bug_2_person_fact_question_falls_back_to_general_chat(self):
        rule_result = _rule_based_route("Who is Sundar Pichai?")
        assert rule_result is None
        agent, intent, _ = _default_route("Who is Sundar Pichai?")
        assert agent == "rag_agent"
        assert intent == "general_chat"

    def test_no_dead_gemini_fallback_function_remains(self):
        """The old `_gemini_route` required GEMINI_API_KEY, which this
        deployment never sets (it runs on Groq) — it silently failed on
        every call and always returned the same default anyway. It was
        removed entirely in favour of _default_route(). This test fails
        loudly if it's ever reintroduced."""
        import app.langgraph.nodes.supervisor as supervisor_module
        assert not hasattr(supervisor_module, "_gemini_route"), (
            "_gemini_route was intentionally removed — it was dead code "
            "that depended on an API key this deployment doesn't set. "
            "See CHANGELOG.md 'Supervisor Routing Audit'."
        )

    def test_cs_concept_beats_generic_catch_all(self):
        """Regression guard: the generic 'what is / explain' catch-all must
        never outrank a specific CS-concept match — it's intentionally the
        lowest-confidence rule in the table."""
        result = _rule_based_route("Explain the difference between SQL and NoSQL databases")
        assert result is not None
        assert result[0] == "rag_agent"
        assert result[2] >= 0.9  # should hit the high-confidence CS pattern, not the 0.75 catch-all

    def test_company_interview_beats_generic_career(self):
        """Regression guard for the interview-vs-career precedence fix."""
        result = _rule_based_route("What is Google's interview process like?")
        assert result is not None
        assert result[0] == "interview_agent"
