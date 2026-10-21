"""
app/utils/ats_scorer.py
───────────────────────
Role-aware ATS scoring engine.

Key improvement over previous version:
  The keyword_score is now TARGET-ROLE AWARE.
  The same resume will produce different keyword scores for
  "ML Engineer" vs "Backend Developer" vs "DevOps Engineer"
  because each role has a distinct required keyword set.

Scoring dimensions (total = 100):
  ┌─────────────────────────────┬────────┐
  │ Dimension                   │ Weight │
  ├─────────────────────────────┼────────┤
  │ Content completeness        │  30 pts│
  │ Keyword density (role-aware)│  25 pts│
  │ Formatting / parseability   │  20 pts│
  │ Experience quality          │  15 pts│
  │ Education & certs           │  10 pts│
  └─────────────────────────────┴────────┘
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.utils.nlp_extractor import ExtractedEntities


# ── Role-specific keyword banks ────────────────────────────────────────────────
# Each role has REQUIRED (must-have) and PREFERRED (nice-to-have) keywords.
# Scores increase when resume text matches these.

ROLE_KEYWORD_BANKS: dict[str, dict[str, list[str]]] = {
    "ml_engineer": {
        "required": [
            "python", "machine learning", "deep learning", "neural network",
            "pytorch", "tensorflow", "scikit-learn", "model training",
            "data preprocessing", "feature engineering",
        ],
        "preferred": [
            "transformer", "llm", "nlp", "computer vision", "mlops",
            "kubernetes", "docker", "aws", "gcp", "wandb", "mlflow",
            "hugging face", "rag", "fine-tuning", "cuda",
        ],
    },
    "backend_developer": {
        "required": [
            "rest api", "api", "database", "sql", "backend",
            "server", "authentication", "deployment", "microservices",
        ],
        "preferred": [
            "fastapi", "django", "flask", "spring", "node", "express",
            "redis", "postgresql", "mysql", "docker", "aws", "ci/cd",
            "grpc", "graphql", "testing", "kafka",
        ],
    },
    "fullstack_developer": {
        "required": [
            "react", "javascript", "html", "css", "api", "database",
            "frontend", "backend",
        ],
        "preferred": [
            "typescript", "next.js", "vue", "angular", "node", "python",
            "sql", "mongodb", "docker", "aws", "testing", "tailwind",
        ],
    },
    "devops_engineer": {
        "required": [
            "docker", "kubernetes", "ci/cd", "linux", "automation",
            "infrastructure", "deployment", "monitoring",
        ],
        "preferred": [
            "terraform", "ansible", "jenkins", "github actions", "prometheus",
            "grafana", "aws", "gcp", "azure", "helm", "argocd", "bash",
        ],
    },
    "data_scientist": {
        "required": [
            "python", "statistics", "data analysis", "machine learning",
            "pandas", "numpy", "visualization",
        ],
        "preferred": [
            "r", "sql", "spark", "hadoop", "tableau", "power bi",
            "scikit-learn", "pytorch", "tensorflow", "a/b testing",
            "hypothesis testing", "regression", "classification",
        ],
    },
    "data_engineer": {
        "required": [
            "python", "sql", "etl", "data pipeline", "database",
            "spark", "data warehouse",
        ],
        "preferred": [
            "airflow", "kafka", "hadoop", "aws", "gcp", "snowflake",
            "redshift", "bigquery", "dbt", "flink", "scala", "hive",
        ],
    },
    "cloud_engineer": {
        "required": [
            "aws", "azure", "gcp", "cloud", "infrastructure",
            "networking", "security", "iam",
        ],
        "preferred": [
            "terraform", "kubernetes", "docker", "serverless", "lambda",
            "ec2", "s3", "rds", "vpc", "cloudformation", "cdk",
        ],
    },
    "ai_engineer": {
        "required": [
            "llm", "python", "api", "machine learning", "prompt",
            "openai", "langchain", "rag",
        ],
        "preferred": [
            "fine-tuning", "vector database", "embeddings", "chromadb",
            "pinecone", "fastapi", "docker", "aws", "hugging face",
            "langgraph", "agent", "groq", "gemini",
        ],
    },
    "frontend_developer": {
        "required": [
            "react", "javascript", "html", "css", "typescript",
            "responsive", "frontend", "ui",
        ],
        "preferred": [
            "next.js", "vue", "angular", "tailwind", "scss",
            "testing", "jest", "webpack", "vite", "accessibility",
            "performance", "web vitals",
        ],
    },
    "mobile_developer": {
        "required": [
            "mobile", "android", "ios", "react native", "flutter",
            "kotlin", "swift", "app",
        ],
        "preferred": [
            "dart", "java", "objective-c", "firebase", "rest api",
            "push notification", "sqlite", "app store", "play store",
        ],
    },
    "cyber_security": {
        "required": [
            "security", "penetration testing", "vulnerability", "network",
            "encryption", "firewall", "siem",
        ],
        "preferred": [
            "kali linux", "metasploit", "burp suite", "owasp",
            "cve", "incident response", "forensics", "soc", "ids", "ips",
        ],
    },
    "default": {
        "required": [
            "programming", "software", "development", "api", "database",
        ],
        "preferred": [
            "python", "java", "javascript", "docker", "aws",
            "agile", "git", "testing", "ci/cd",
        ],
    },
}

# Map common role title keywords → bank key
_ROLE_KEY_MAP = {
    "ml engineer":           "ml_engineer",
    "machine learning":      "ml_engineer",
    "ai engineer":           "ai_engineer",
    "artificial intelligence": "ai_engineer",
    "data scientist":        "data_scientist",
    "data science":          "data_scientist",
    "data engineer":         "data_engineer",
    "data engineering":      "data_engineer",
    "backend":               "backend_developer",
    "back-end":              "backend_developer",
    "back end":              "backend_developer",
    "fullstack":             "fullstack_developer",
    "full stack":            "fullstack_developer",
    "full-stack":            "fullstack_developer",
    "frontend":              "frontend_developer",
    "front-end":             "frontend_developer",
    "front end":             "frontend_developer",
    "devops":                "devops_engineer",
    "sre":                   "devops_engineer",
    "cloud":                 "cloud_engineer",
    "mobile":                "mobile_developer",
    "android":               "mobile_developer",
    "ios":                   "mobile_developer",
    "flutter":               "mobile_developer",
    "security":              "cyber_security",
    "cybersecurity":         "cyber_security",
    "penetration":           "cyber_security",
}


def _resolve_role_bank(target_role: str | None) -> dict[str, list[str]]:
    """Map a free-text role title to the closest keyword bank."""
    if not target_role:
        return ROLE_KEYWORD_BANKS["default"]
    role_lower = target_role.lower()
    for keyword, bank_key in _ROLE_KEY_MAP.items():
        if keyword in role_lower:
            return ROLE_KEYWORD_BANKS[bank_key]
    return ROLE_KEYWORD_BANKS["default"]


# ── Universal ATS power words ──────────────────────────────────────────────────
ATS_POWER_WORDS: set[str] = {
    "achieved", "built", "collaborated", "delivered", "designed", "developed",
    "engineered", "improved", "implemented", "increased", "launched", "led",
    "managed", "optimised", "optimized", "reduced", "scaled", "shipped",
    "streamlined", "transformed", "automated", "architected", "deployed",
}

QUANTIFIER_PATTERN = re.compile(
    r"\b(\d+[\.,]?\d*\s*(?:%|percent|x|times|million|billion|k|users|requests|"
    r"ms|seconds|hours|days|months|years|lines|commits|deployments|services))\b",
    re.IGNORECASE,
)

CONTACT_FIELDS_NEEDED = {"email", "phone", "linkedin"}
SECTION_NAMES_NEEDED  = {"experience", "education", "skills"}


@dataclass
class ATSScoreResult:
    ats_score:        float = 0.0
    formatting_score: float = 0.0
    content_score:    float = 0.0
    keyword_score:    float = 0.0
    experience_score: float = 0.0
    education_score:  float = 0.0

    strengths:        list[str] = field(default_factory=list)
    weaknesses:       list[str] = field(default_factory=list)
    keywords_found:   list[str] = field(default_factory=list)
    keywords_missing: list[str] = field(default_factory=list)
    grade:            str = "F"
    verdict:          str = ""
    seniority_match:  str = "undetected"
    target_role:      str | None = None


def calculate_ats_score(
    parsed_text:  str,
    entities:     ExtractedEntities,
    sections:     dict[str, str],
    word_count:   int,
    page_count:   int,
    target_role:  str | None = None,
) -> ATSScoreResult:
    result = ATSScoreResult(target_role=target_role)

    result.content_score    = _score_content(entities, sections, word_count, result)
    result.keyword_score    = _score_keywords(parsed_text, entities, result, target_role)
    result.formatting_score = _score_formatting(parsed_text, sections, page_count, word_count)
    result.experience_score = _score_experience(parsed_text, entities, sections)
    result.education_score  = _score_education(entities)

    # Weighted composite
    result.ats_score = round(
        result.content_score    * 0.30
        + result.keyword_score  * 0.25
        + result.formatting_score * 0.20
        + result.experience_score * 0.15
        + result.education_score  * 0.10,
        2,
    )

    result.grade   = _score_to_grade(result.ats_score)
    result.verdict = _build_verdict(result)
    result.seniority_match = _determine_seniority_match(entities, target_role)

    return result


# ── Dimension scorers ─────────────────────────────────────────────────────────

def _score_content(
    entities:  ExtractedEntities,
    sections:  dict[str, str],
    word_count: int,
    result:    ATSScoreResult,
) -> float:
    score = 0.0
    strengths: list[str] = []
    weaknesses: list[str] = []

    # Contact completeness (20 pts)
    contact_present = {k for k in CONTACT_FIELDS_NEEDED if k in entities.contact}
    contact_pts = (len(contact_present) / len(CONTACT_FIELDS_NEEDED)) * 20
    score += contact_pts
    if contact_pts == 20:
        strengths.append("Complete contact information with LinkedIn")
    elif contact_pts < 10:
        weaknesses.append("Missing key contact fields (phone/LinkedIn)")

    # Required sections (30 pts)
    section_keys = set(sections.keys())
    present = SECTION_NAMES_NEEDED & section_keys
    section_pts = (len(present) / len(SECTION_NAMES_NEEDED)) * 30
    score += section_pts
    missing_sections = SECTION_NAMES_NEEDED - section_keys
    for sec in missing_sections:
        weaknesses.append(f"Missing '{sec}' section")

    # Word count (20 pts)
    if word_count >= 400:
        score += 20
        if word_count >= 700:
            strengths.append(f"Comprehensive resume ({word_count} words)")
    elif word_count >= 200:
        score += 10
        weaknesses.append(f"Resume is brief ({word_count} words) — aim for 400+")
    else:
        weaknesses.append(f"Very short resume ({word_count} words)")

    # Skills count (15 pts)
    n_skills = len(entities.technical_skills)
    if n_skills >= 15:
        score += 15
        strengths.append(f"Strong technical skill set ({n_skills} skills detected)")
    elif n_skills >= 10:
        score += 10
    elif n_skills >= 5:
        score += 6
    elif n_skills >= 2:
        score += 3
    else:
        weaknesses.append("Very few technical skills detected")

    # Projects section bonus (up to 10 pts extra absorbed into content)
    if "projects" in section_keys:
        score = min(100.0, score + 5)
        strengths.append("Has dedicated Projects section")

    # Certifications bonus (15 pts)
    if entities.certifications:
        cert_pts = min(15.0, len(entities.certifications) * 5)
        score = min(100.0, score + cert_pts)
        strengths.append(f"{len(entities.certifications)} certification(s) listed")

    result.strengths  = strengths
    result.weaknesses = weaknesses

    return min(100.0, round(score, 2))


def _score_keywords(
    text:        str,
    entities:    ExtractedEntities,
    result:      ATSScoreResult,
    target_role: str | None,
) -> float:
    """
    Role-aware keyword scoring.

    For a given target_role, the resume is scored against that role's
    specific required and preferred keywords.
    A resume for "ML Engineer" gets credit for 'pytorch', 'model training' etc.
    The same resume for "Backend Developer" gets credit for 'rest api', 'sql' etc.
    This ensures different roles produce different ATS scores.
    """
    text_lower = text.lower()
    score      = 0.0
    found_role_keywords:   list[str] = []
    missing_role_keywords: list[str] = []

    # 1. Role-specific keywords (50 pts) ────────────────────────────────────────
    bank = _resolve_role_bank(target_role)
    required  = bank["required"]
    preferred = bank["preferred"]

    req_found   = [k for k in required  if k.lower() in text_lower]
    pref_found  = [k for k in preferred if k.lower() in text_lower]
    req_missing = [k for k in required  if k.lower() not in text_lower]

    # Required: up to 35 pts proportional
    req_pct = len(req_found) / max(1, len(required))
    score  += req_pct * 35

    # Preferred: up to 15 pts proportional
    pref_pct = len(pref_found) / max(1, len(preferred))
    score   += pref_pct * 15

    found_role_keywords  = req_found + pref_found
    missing_role_keywords = req_missing[:8]  # top 8 missing

    # 2. ATS power action verbs (25 pts) ────────────────────────────────────────
    found_power = [w for w in ATS_POWER_WORDS if w in text_lower]
    score      += min(25.0, len(found_power) * 2.5)

    # 3. Quantified achievements (15 pts) ───────────────────────────────────────
    quant_matches = QUANTIFIER_PATTERN.findall(text)
    score        += min(15.0, len(quant_matches) * 3)

    # 4. Skills breadth from NLP (10 pts) ───────────────────────────────────────
    n = len(entities.technical_skills)
    score += min(10.0, n * 0.8)

    # Set result fields
    result.keywords_found   = found_role_keywords[:20]
    result.keywords_missing = missing_role_keywords

    if result.strengths is None:
        result.strengths = []
    if quant_matches:
        result.strengths.append(f"{len(quant_matches)} quantified achievement(s) found")
    if len(found_power) >= 5:
        result.strengths.append(f"Strong use of action verbs ({len(found_power)} found)")

    return min(100.0, round(score, 2))


def _score_formatting(
    text:      str,
    sections:  dict[str, str],
    page_count: int,
    word_count: int,
) -> float:
    score = 0.0

    # Page count (25 pts) — 1-2 pages ideal
    if page_count == 1:
        score += 25
    elif page_count == 2:
        score += 20
    elif page_count <= 3:
        score += 10
    else:
        score += 5  # too long

    # Consistent line lengths — no garbled PDF (25 pts)
    lines = [l for l in text.split("\n") if l.strip()]
    if lines:
        avg_len = sum(len(l) for l in lines) / len(lines)
        if 20 <= avg_len <= 120:
            score += 25
        elif avg_len > 0:
            score += 12

    # No excessive special characters (25 pts)
    special_ratio = len(re.findall(r"[^\w\s.,;:()\-/]", text)) / max(1, len(text))
    if special_ratio < 0.02:
        score += 25
    elif special_ratio < 0.05:
        score += 15

    # Section structure (25 pts)
    if len(sections) >= 4:
        score += 25
    elif len(sections) >= 2:
        score += 15
    elif len(sections) >= 1:
        score += 8

    return min(100.0, round(score, 2))


def _score_experience(
    text:     str,
    entities: ExtractedEntities,
    sections: dict[str, str],
) -> float:
    score = 0.0

    # Years of experience (40 pts)
    yoe = entities.total_years_exp
    if yoe >= 5:
        score += 40
    elif yoe >= 3:
        score += 30
    elif yoe >= 1:
        score += 20
    elif yoe > 0:
        score += 10

    # Quantified achievements in experience section (30 pts)
    exp_text = sections.get("experience", text)
    quants   = QUANTIFIER_PATTERN.findall(exp_text)
    score   += min(30.0, len(quants) * 6)

    # Action verb usage (30 pts)
    exp_lower = exp_text.lower()
    verbs_used = [v for v in ATS_POWER_WORDS if v in exp_lower]
    score     += min(30.0, len(verbs_used) * 3)

    return min(100.0, round(score, 2))


def _score_education(entities: ExtractedEntities) -> float:
    level_scores = {
        "PhD":       100.0,
        "Masters":    85.0,
        "Bachelors":  70.0,
        "Diploma":    50.0,
        "Associate":  40.0,
        "unknown":    20.0,
    }
    base = level_scores.get(entities.education_level, 20.0)
    cert_bonus = min(30.0, len(entities.certifications) * 10)
    return min(100.0, base + cert_bonus)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_to_grade(score: float) -> str:
    if score >= 85:  return "A"
    if score >= 70:  return "B"
    if score >= 55:  return "C"
    if score >= 40:  return "D"
    return "F"


def _build_verdict(result: ATSScoreResult) -> str:
    role_ctx = f" for {result.target_role}" if result.target_role else ""
    if result.ats_score >= 85:
        return f"Excellent — highly ATS-compatible resume{role_ctx}. Strong chance of passing automated screening."
    if result.ats_score >= 70:
        return f"Good — resume will likely pass ATS filters{role_ctx}. Minor improvements recommended."
    if result.ats_score >= 55:
        return f"Fair — resume may pass ATS{role_ctx} but needs targeted improvements."
    if result.ats_score >= 40:
        return f"Weak — resume is likely to be filtered out{role_ctx}. Significant revisions needed."
    return f"Poor — resume needs a complete overhaul{role_ctx} before submitting to ATS portals."


def _determine_seniority_match(
    entities:    ExtractedEntities,
    target_role: str | None,
) -> str:
    detected = entities.detected_seniority or "Mid-Level"
    if not target_role:
        return "undetected"
    role_lower = target_role.lower()
    is_senior_role = any(w in role_lower for w in ["senior", "sr.", "lead", "principal", "staff", "architect"])
    is_junior_role = any(w in role_lower for w in ["junior", "jr.", "associate", "entry", "intern", "fresher"])
    if is_senior_role:
        return "match" if "Senior" in detected or "Principal" in detected else "below"
    if is_junior_role:
        return "above" if "Senior" in detected or "Principal" in detected else "match"
    return "match"
