"""
app/agents/interview_evaluator.py
──────────────────────────────────
Rule-based answer evaluation engine.

Scores five dimensions deterministically (no LLM needed):
  confidence_score     — assertive language, first-person, concrete claims
  technical_score      — presence of technical keywords for the role/topic
  communication_score  — structure, length, clarity indicators
  relevance_score      — answer addresses the question topic
  completeness_score   — covers expected components (STAR, definition+example, etc.)

Each dimension returns 0–100. These stable numbers are then sent to
Gemini for narrative feedback generation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ── Scoring signals ───────────────────────────────────────────────────────────

_CONFIDENCE_POSITIVE = [
    r"\bi (have|led|built|designed|implemented|created|achieved|delivered|managed|drove|owned)\b",
    r"\bsuccessfully\b", r"\baccomplished\b", r"\bproudly\b",
    r"\bin my experience\b", r"\bmy approach\b", r"\bi believe\b",
    r"\bi am confident\b", r"\bi demonstrated\b", r"\bmy contribution\b",
]
_CONFIDENCE_NEGATIVE = [
    r"\bi think maybe\b", r"\bi'm not sure\b", r"\bprobably\b",
    r"\bi guess\b", r"\bsomewhat\b", r"\bkind of\b", r"\bi don'?t know\b",
    r"\bnot really\b", r"\bnot sure if\b",
]

_STAR_INDICATORS = {
    "situation": [r"\bsituation\b", r"\bcontext\b", r"\bworking at\b", r"\bwas working on\b", r"\bour team\b", r"\bthe project\b"],
    "task":      [r"\bmy role\b", r"\bresponsible for\b", r"\btasked with\b", r"\bi needed to\b", r"\bmy goal\b"],
    "action":    [r"\bi decided\b", r"\bi implemented\b", r"\bmy approach\b", r"\bstep\b", r"\bi first\b", r"\bi then\b"],
    "result":    [r"\bresult\b", r"\boutcome\b", r"\bimpact\b", r"\breduced\b", r"\bimproved\b", r"\bincreased\b", r"\bdelivered\b", r"\b\d+%\b", r"\bsaved\b"],
}

_TECHNICAL_KEYWORDS_BY_TOPIC: dict[str, list[str]] = {
    "system_design": [
        "scalability", "load balancing", "sharding", "caching", "cdn",
        "microservices", "api gateway", "message queue", "kafka",
        "database", "replication", "consistency", "availability",
        "rate limiting", "horizontal", "vertical", "partition",
    ],
    "data_structures": [
        "time complexity", "space complexity", "big o",
        "array", "linked list", "tree", "graph", "hash",
        "stack", "queue", "heap", "recursion", "iteration",
    ],
    "algorithms": [
        "dynamic programming", "memoization", "greedy", "divide",
        "backtracking", "two pointer", "sliding window", "binary search",
        "traversal", "bfs", "dfs", "sorting", "complexity",
    ],
    "databases": [
        "acid", "normalization", "index", "join", "transaction",
        "nosql", "sql", "query", "schema", "relation", "primary key",
        "foreign key", "constraint", "deadlock", "isolation",
    ],
    "os_networking": [
        "process", "thread", "deadlock", "mutex", "semaphore",
        "tcp", "udp", "http", "dns", "osi", "protocol",
        "socket", "handshake", "packet", "routing",
    ],
    "python": [
        "decorator", "generator", "comprehension", "gil",
        "asyncio", "coroutine", "class", "inheritance",
        "lambda", "closure", "iterator",
    ],
    "java": [
        "jvm", "garbage collection", "thread", "synchronized",
        "interface", "abstract", "generic", "collection",
        "stream", "lambda", "spring", "hibernate",
    ],
    "general_technical": [
        "implement", "algorithm", "data structure", "function",
        "class", "api", "database", "server", "client",
        "code", "test", "debug", "performance", "optimize",
    ],
}

_COMMUNICATION_GOOD = [
    r"\bfirstly\b", r"\bfirst\b", r"\bsecond(ly)?\b", r"\bthird(ly)?\b",
    r"\bfinally\b", r"\bin conclusion\b", r"\bto summarise\b",
    r"\bfor example\b", r"\bspecifically\b", r"\bin addition\b",
    r"\bhowever\b", r"\btherefore\b", r"\bas a result\b",
]


@dataclass
class EvaluationResult:
    confidence_score:    float
    technical_score:     float
    communication_score: float
    relevance_score:     float
    completeness_score:  float
    overall_score:       float
    star_breakdown:      dict  = field(default_factory=dict)
    keywords_used:       list  = field(default_factory=list)
    keywords_missed:     list  = field(default_factory=list)
    word_count:          int   = 0
    has_metrics:         bool  = False


def evaluate_answer(
    question:       str,
    answer:         str,
    question_type:  str,
    target_role:    str | None = None,
    topic:          str | None = None,
) -> EvaluationResult:
    """
    Score an interview answer across five dimensions.
    Returns EvaluationResult with all scores 0–100.
    """
    if not answer or len(answer.strip()) < 10:
        return EvaluationResult(0, 0, 0, 0, 0, 0)

    text      = answer.lower().strip()
    words     = text.split()
    word_count = len(words)

    confidence   = _score_confidence(text, word_count)
    technical    = _score_technical(text, question_type, topic, target_role)
    communication = _score_communication(text, word_count)
    relevance    = _score_relevance(text, question)
    completeness, star_bd = _score_completeness(text, question_type, word_count)

    # Keywords analysis
    used, missed = _keyword_analysis(text, question_type, topic)
    has_metrics  = bool(re.search(r"\b\d+[\.,]?\d*\s*(%|percent|x|users|ms|seconds|million|k|lpa)\b", text))

    # Weighted overall
    weights = {
        "confidence":    0.20,
        "technical":     0.30,
        "communication": 0.20,
        "relevance":     0.20,
        "completeness":  0.10,
    }
    # Adjust weights by question type
    if question_type in ("technical", "system_design", "coding"):
        weights = {"confidence": 0.15, "technical": 0.40, "communication": 0.15, "relevance": 0.20, "completeness": 0.10}
    elif question_type in ("hr", "behavioural", "culture_fit"):
        weights = {"confidence": 0.25, "technical": 0.10, "communication": 0.25, "relevance": 0.20, "completeness": 0.20}

    overall = round(
        confidence    * weights["confidence"]
        + technical   * weights["technical"]
        + communication * weights["communication"]
        + relevance   * weights["relevance"]
        + completeness * weights["completeness"],
        2,
    )

    return EvaluationResult(
        confidence_score=confidence,
        technical_score=technical,
        communication_score=communication,
        relevance_score=relevance,
        completeness_score=completeness,
        overall_score=overall,
        star_breakdown=star_bd,
        keywords_used=used,
        keywords_missed=missed,
        word_count=word_count,
        has_metrics=has_metrics,
    )


# ── Dimension scorers ─────────────────────────────────────────────────────────

def _score_confidence(text: str, word_count: int) -> float:
    pos = sum(1 for p in _CONFIDENCE_POSITIVE if re.search(p, text))
    neg = sum(1 for p in _CONFIDENCE_NEGATIVE if re.search(p, text))
    # Length also signals confidence (short = uncertain)
    length_pts = min(30.0, word_count * 0.5)
    score = min(100.0, pos * 12 - neg * 8 + length_pts + 20)
    return max(0.0, round(score, 2))


def _score_technical(
    text: str,
    question_type: str,
    topic: str | None,
    target_role: str | None,
) -> float:
    if question_type in ("hr", "culture_fit", "behavioural"):
        return 70.0  # not evaluated for non-technical questions

    # Determine which keyword pool to use
    pool_key = None
    if topic and topic in _TECHNICAL_KEYWORDS_BY_TOPIC:
        pool_key = topic
    elif target_role:
        role_lower = target_role.lower()
        if "python" in role_lower:
            pool_key = "python"
        elif "java" in role_lower:
            pool_key = "java"
        elif "data" in role_lower or "ml" in role_lower or "ai" in role_lower:
            pool_key = "general_technical"

    keywords = (
        _TECHNICAL_KEYWORDS_BY_TOPIC.get(pool_key, [])
        + _TECHNICAL_KEYWORDS_BY_TOPIC["general_technical"]
    )

    if not keywords:
        return 50.0

    found = [kw for kw in keywords if kw in text]
    score = min(100.0, (len(found) / max(1, len(keywords))) * 200)
    return round(score, 2)


def _score_communication(text: str, word_count: int) -> float:
    structure_pts = sum(4.0 for p in _COMMUNICATION_GOOD if re.search(p, text))
    # Ideal length: 80–250 words
    if word_count < 20:
        length_pts = 10.0
    elif word_count < 50:
        length_pts = 30.0
    elif word_count <= 250:
        length_pts = 50.0
    else:
        length_pts = max(30.0, 50.0 - (word_count - 250) * 0.1)

    # Check for run-on sentences (very long lines without punctuation)
    clarity_penalty = 0.0
    avg_sentence_len = word_count / max(1, text.count(".") + text.count("!") + text.count("?"))
    if avg_sentence_len > 40:
        clarity_penalty = 10.0

    score = min(100.0, length_pts + structure_pts - clarity_penalty)
    return max(0.0, round(score, 2))


def _score_relevance(text: str, question: str) -> float:
    """Check if the answer contains key words from the question."""
    q_words = {w for w in question.lower().split() if len(w) > 3}
    q_words -= {"what", "when", "where", "which", "would", "could", "should",
                "tell", "describe", "explain", "give", "have", "your", "you",
                "about", "with", "that", "this", "from", "them"}
    if not q_words:
        return 65.0
    found = sum(1 for w in q_words if w in text)
    score = min(100.0, (found / len(q_words)) * 130)
    return round(score, 2)


def _score_completeness(text: str, question_type: str, word_count: int) -> tuple[float, dict]:
    star_bd: dict[str, bool] = {}

    if question_type in ("behavioural", "hr", "situational"):
        # STAR method check
        for component, patterns in _STAR_INDICATORS.items():
            star_bd[component] = any(re.search(p, text) for p in patterns)
        present = sum(1 for v in star_bd.values() if v)
        base_score = (present / 4) * 70
        # Bonus for metrics
        if re.search(r"\b\d+\b", text):
            base_score += 15
        if word_count >= 80:
            base_score += 15
        return round(min(100.0, base_score), 2), star_bd

    elif question_type in ("technical", "system_design", "coding"):
        score = 0.0
        if word_count >= 50:  score += 25
        if word_count >= 100: score += 15
        # Definition + example pattern
        if re.search(r"\bfor example\b|\bsuch as\b|\binstance\b", text):
            score += 20
        if re.search(r"\btrade.?off\b|\bpros? and cons?\b|\bdrawback\b|\badvantage\b", text):
            score += 20
        if re.search(r"\btime complexity\b|\bo\(\b|\bspace\b", text):
            score += 20
        return round(min(100.0, score), 2), {}

    else:
        score = min(100.0, word_count * 0.5 + 20)
        return round(score, 2), {}


def _keyword_analysis(text: str, question_type: str, topic: str | None) -> tuple[list[str], list[str]]:
    pool_key = topic if topic in _TECHNICAL_KEYWORDS_BY_TOPIC else "general_technical"
    kws = _TECHNICAL_KEYWORDS_BY_TOPIC.get(pool_key, [])
    used   = [kw for kw in kws if kw in text]
    missed = [kw for kw in kws if kw not in text][:5]
    return used[:8], missed
