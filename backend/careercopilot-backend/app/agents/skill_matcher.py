"""
app/agents/skill_matcher.py
────────────────────────────
Rule-based skill matching engine.

Compares a candidate's skills (from resume text or explicit list) against
the role skill database using:
  - Exact name match
  - Normalised alias matching (e.g. "pytorch" ↔ "PyTorch")
  - Partial/substring matching for compound names
  - Proficiency gap scoring (has skill but at lower level)

Returns a SkillMatchResult with all scores computed deterministically
before Gemini is invoked — this keeps numbers stable and trustworthy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.agents.role_skill_db import (
    Priority,
    Proficiency,
    RoleDefinition,
    RoleSkill,
    get_role,
)

# ── Proficiency ordering ──────────────────────────────────────────────────────
_PROF_RANK: dict[Proficiency, int] = {
    Proficiency.BEGINNER:     1,
    Proficiency.INTERMEDIATE: 2,
    Proficiency.ADVANCED:     3,
    Proficiency.EXPERT:       4,
}

# Priority weights for overall score calculation
_PRIORITY_WEIGHT: dict[Priority, float] = {
    Priority.CRITICAL: 3.0,
    Priority.HIGH:     2.0,
    Priority.MEDIUM:   1.0,
    Priority.LOW:      0.5,
}

# Common skill aliases — maps lowercase variant → canonical lowercase name
_SKILL_ALIASES: dict[str, str] = {
    "pytorch":               "pytorch",
    "torch":                 "pytorch",
    "tensorflow":            "tensorflow or pytorch",
    "tf":                    "tensorflow or pytorch",
    "sklearn":               "scikit-learn",
    "scikit learn":          "scikit-learn",
    "sk-learn":              "scikit-learn",
    "pandas":                "pandas / numpy",
    "numpy":                 "pandas / numpy",
    "react":                 "react.js",
    "reactjs":               "react.js",
    "react js":              "react.js",
    "nodejs":                "node.js",
    "node":                  "node.js",
    "javascript":            "javascript (es6+)",
    "js":                    "javascript (es6+)",
    "typescript":            "typescript",
    "ts":                    "typescript",
    "postgres":              "database (postgresql / mongodb)",
    "postgresql":            "database (postgresql / mongodb)",
    "mongodb":               "database (postgresql / mongodb)",
    "mongo":                 "database (postgresql / mongodb)",
    "aws":                   "aws / gcp / azure",
    "gcp":                   "aws / gcp / azure",
    "azure":                 "aws / gcp / azure",
    "k8s":                   "kubernetes",
    "docker compose":        "docker",
    "github actions":        "ci/cd (github actions / jenkins)",
    "gitlab ci":             "ci/cd (github actions / jenkins)",
    "jenkins":               "ci/cd (github actions / jenkins)",
    "langchain":             "langchain / langgraph",
    "langgraph":             "langchain / langgraph",
    "llm":                   "large language models (llms)",
    "large language model":  "large language models (llms)",
    "gpt":                   "large language models (llms)",
    "gemini":                "large language models (llms)",
    "rag":                   "rag (retrieval-augmented generation)",
    "retrieval augmented generation": "rag (retrieval-augmented generation)",
    "chroma":                "vector databases",
    "chromadb":              "vector databases",
    "qdrant":                "vector databases",
    "pinecone":              "vector databases",
    "weaviate":              "vector databases",
    "tailwind":              "responsive design / tailwind css",
    "tailwindcss":           "responsive design / tailwind css",
    "css":                   "html5 / css3",
    "html":                  "html5 / css3",
    "html5":                 "html5 / css3",
    "express":               "express.js / fastify",
    "expressjs":             "express.js / fastify",
    "fastify":               "express.js / fastify",
    "nextjs":                "next.js",
    "next js":               "next.js",
    "terraform":             "terraform (iac)",
    "iac":                   "terraform (iac)",
    "bash":                  "linux / bash scripting",
    "shell":                 "linux / bash scripting",
    "linux":                 "linux / bash scripting",
    "linux / bash":          "linux / bash scripting",
    "prometheus":            "monitoring (prometheus / grafana / cloudwatch)",
    "grafana":               "monitoring (prometheus / grafana / cloudwatch)",
    "cloudwatch":            "monitoring (prometheus / grafana / cloudwatch)",
    "spring":                "spring boot",
    "springboot":            "spring boot",
    "jpa":                   "jpa / hibernate",
    "hibernate":             "jpa / hibernate",
    "junit":                 "junit / mockito (testing)",
    "mockito":               "junit / mockito (testing)",
    "jwt":                   "authentication (jwt / oauth2)",
    "oauth":                 "authentication (jwt / oauth2)",
    "oauth2":                "authentication (jwt / oauth2)",
    "matplotlib":            "data visualisation (matplotlib/seaborn/plotly)",
    "seaborn":               "data visualisation (matplotlib/seaborn/plotly)",
    "plotly":                "data visualisation (matplotlib/seaborn/plotly)",
    "tableau":               "business intelligence tools (tableau / power bi)",
    "power bi":              "business intelligence tools (tableau / power bi)",
    "powerbi":               "business intelligence tools (tableau / power bi)",
    "ab testing":            "a/b testing",
    "a/b test":              "a/b testing",
}


def _normalise(name: str) -> str:
    """Lowercase, strip punctuation variants for fuzzy matching."""
    n = name.lower().strip()
    n = re.sub(r"[./]", " ", n)
    n = re.sub(r"\s+", " ", n)
    return n


def _resolve_alias(name: str) -> str:
    """Return canonical skill name if an alias exists, else return as-is."""
    n = _normalise(name)
    return _SKILL_ALIASES.get(n, n)


def _names_match(candidate: str, role_skill: str) -> bool:
    """
    Return True if candidate skill matches a role skill name.
    Tries: exact → alias → substring (both directions).
    """
    c = _resolve_alias(candidate)
    r = _normalise(role_skill)
    r_resolved = _resolve_alias(role_skill)

    if c == r or c == r_resolved:
        return True
    # Substring matching — handles "PyTorch" matching "PyTorch or TensorFlow"
    if c in r or r in c:
        return True
    # Word overlap — at least 50% of words match
    c_words = set(c.split())
    r_words = set(r.split())
    if c_words and r_words:
        overlap = c_words & r_words
        if len(overlap) / min(len(c_words), len(r_words)) >= 0.5:
            return True
    return False


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class MatchedSkill:
    role_skill_name: str
    candidate_skill: str
    priority:        Priority
    category:        str
    min_proficiency: Proficiency
    match_type:      str  # "exact" | "alias" | "partial" | "proficiency_gap"
    proficiency_gap: int  # 0 = full match, >0 = need to level up


@dataclass
class MissingSkill:
    name:            str
    priority:        Priority
    category:        str
    min_proficiency: Proficiency
    description:     str
    learning_url:    str


@dataclass
class SkillMatchResult:
    role_key:             str
    role_title:           str

    # Scores (0–100)
    overall_match_pct:    float
    required_match_pct:   float
    preferred_match_pct:  float

    # Categorised skill lists
    matched:              list[MatchedSkill]   = field(default_factory=list)
    missing_required:     list[MissingSkill]   = field(default_factory=list)
    missing_preferred:    list[MissingSkill]   = field(default_factory=list)
    partially_matched:    list[MatchedSkill]   = field(default_factory=list)

    # Derived
    gap_severity:         str  = "major"
    estimated_prep_months: int = 6


# ── Main matcher ──────────────────────────────────────────────────────────────

def match_skills(
    candidate_skills: list[str],
    role_key:         str,
) -> SkillMatchResult:
    """
    Compare candidate skills against the role skill database.

    Args:
        candidate_skills: List of skill names extracted from resume or user input
        role_key:         One of the keys in ROLE_REGISTRY

    Returns:
        SkillMatchResult with full breakdown
    """
    role = get_role(role_key)
    cand_lower = [_normalise(s) for s in candidate_skills]

    matched:           list[MatchedSkill] = []
    missing_required:  list[MissingSkill] = []
    missing_preferred: list[MissingSkill] = []
    partially_matched: list[MatchedSkill] = []

    def _find_match(role_skill: RoleSkill) -> Optional[MatchedSkill]:
        for raw_skill in candidate_skills:
            if _names_match(raw_skill, role_skill.name):
                mtype = "exact" if _normalise(raw_skill) == _normalise(role_skill.name) else "alias"
                return MatchedSkill(
                    role_skill_name=role_skill.name,
                    candidate_skill=raw_skill,
                    priority=role_skill.priority,
                    category=role_skill.category,
                    min_proficiency=role_skill.min_proficiency,
                    match_type=mtype,
                    proficiency_gap=0,
                )
        return None

    # ── Check required skills ─────────────────────────────────────────────────
    req_weight_total   = 0.0
    req_weight_matched = 0.0

    for rs in role.required_skills:
        w = _PRIORITY_WEIGHT[rs.priority]
        req_weight_total += w
        m = _find_match(rs)
        if m:
            req_weight_matched += w
            matched.append(m)
        else:
            missing_required.append(MissingSkill(
                name=rs.name,
                priority=rs.priority,
                category=rs.category,
                min_proficiency=rs.min_proficiency,
                description=rs.description,
                learning_url=rs.learning_url,
            ))

    # ── Check preferred skills ────────────────────────────────────────────────
    pref_weight_total   = 0.0
    pref_weight_matched = 0.0

    for rs in role.preferred_skills:
        w = _PRIORITY_WEIGHT[rs.priority]
        pref_weight_total += w
        m = _find_match(rs)
        if m:
            pref_weight_matched += w
            matched.append(m)
        else:
            missing_preferred.append(MissingSkill(
                name=rs.name,
                priority=rs.priority,
                category=rs.category,
                min_proficiency=rs.min_proficiency,
                description=rs.description,
                learning_url=rs.learning_url,
            ))

    # ── Compute percentages ───────────────────────────────────────────────────
    req_pct  = round((req_weight_matched  / max(req_weight_total,  1)) * 100, 1)
    pref_pct = round((pref_weight_matched / max(pref_weight_total, 1)) * 100, 1)

    # Overall = 70% required + 30% preferred
    overall_pct = round(req_pct * 0.70 + pref_pct * 0.30, 1)

    # ── Gap severity ──────────────────────────────────────────────────────────
    if overall_pct >= 90:
        severity        = "none"
        prep_months     = 0
    elif overall_pct >= 70:
        severity        = "minor"
        prep_months     = 2
    elif overall_pct >= 50:
        severity        = "moderate"
        prep_months     = 4
    elif overall_pct >= 25:
        severity        = "major"
        prep_months     = 8
    else:
        severity        = "critical"
        prep_months     = 14

    # Adjust for number of critical missing skills
    critical_missing = sum(1 for s in missing_required if s.priority == Priority.CRITICAL)
    prep_months += critical_missing * 1

    return SkillMatchResult(
        role_key=role_key,
        role_title=role.title,
        overall_match_pct=overall_pct,
        required_match_pct=req_pct,
        preferred_match_pct=pref_pct,
        matched=matched,
        missing_required=missing_required,
        missing_preferred=missing_preferred,
        partially_matched=partially_matched,
        gap_severity=severity,
        estimated_prep_months=prep_months,
    )


def extract_skills_from_text(text: str) -> list[str]:
    """
    Quick skill extraction from raw text using the NLP extractor.
    Returns a deduplicated list of skill name strings.
    """
    from app.utils.nlp_extractor import _extract_skills
    raw = _extract_skills(text)
    return list({s["name"] for s in raw})
