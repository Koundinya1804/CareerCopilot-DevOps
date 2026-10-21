"""
app/utils/nlp_extractor.py
──────────────────────────
Rule-based NLP extractor for resume entities.

Extracts without any ML model (no NLTK/spaCy dependency):
  - Skills  : matched against a curated taxonomy of 300+ terms
  - Contact : regex patterns for email, phone, URLs
  - Dates   : employment date ranges
  - Years of experience : computed from date ranges
  - Certifications : pattern-matched against known cert names
  - Education level : degree keyword detection
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# ── Skill Taxonomy ─────────────────────────────────────────────────────────────
SKILL_TAXONOMY: dict[str, list[str]] = {
    "language": [
        "python", "java", "javascript", "typescript", "c++", "c#", "c", "go", "golang",
        "rust", "kotlin", "swift", "ruby", "php", "scala", "r", "matlab", "perl",
        "bash", "shell", "powershell", "sql", "plsql", "dart", "elixir", "haskell",
        "lua", "groovy", "objective-c", "vba", "cobol", "fortran", "assembly",
    ],
    "framework": [
        "react", "angular", "vue", "next.js", "nuxt", "svelte", "fastapi", "django",
        "flask", "express", "nest.js", "spring", "spring boot", "laravel", "rails",
        "asp.net", ".net", "blazor", "flutter", "react native", "ionic", "electron",
        "fastify", "gin", "fiber", "actix", "axum", "phoenix", "pytorch", "tensorflow",
        "keras", "scikit-learn", "sklearn", "hugging face", "langchain", "langgraph",
        "pandas", "numpy", "scipy", "matplotlib", "seaborn", "plotly", "streamlit",
        "gradio", "celery", "sqlalchemy", "prisma", "typeorm", "hibernate",
    ],
    "database": [
        "mysql", "postgresql", "postgres", "sqlite", "mongodb", "redis", "elasticsearch",
        "cassandra", "dynamodb", "firestore", "supabase", "cockroachdb", "neo4j",
        "influxdb", "timescaledb", "qdrant", "pinecone", "weaviate", "chroma",
        "oracle", "ms sql", "sql server", "mariadb", "couchdb", "arangodb",
    ],
    "cloud": [
        "aws", "gcp", "azure", "heroku", "vercel", "netlify", "digitalocean",
        "ec2", "s3", "lambda", "ecs", "eks", "rds", "cloudfront", "route53",
        "iam", "cloudwatch", "sqs", "sns", "kinesis", "glue", "athena", "emr",
        "bigquery", "cloud run", "cloud functions", "gke", "cloud storage",
        "azure devops", "blob storage", "app service", "azure functions",
    ],
    "devops": [
        "docker", "kubernetes", "k8s", "helm", "terraform", "ansible", "puppet",
        "chef", "jenkins", "github actions", "gitlab ci", "circleci", "travis ci",
        "argocd", "flux", "prometheus", "grafana", "elk", "loki", "jaeger",
        "nginx", "apache", "caddy", "traefik", "istio", "linkerd",
    ],
    "tool": [
        "git", "github", "gitlab", "bitbucket", "jira", "confluence", "notion",
        "figma", "sketch", "postman", "insomnia", "vs code", "intellij", "pycharm",
        "vim", "neovim", "linux", "ubuntu", "debian", "macos", "windows",
        "webpack", "vite", "babel", "eslint", "prettier", "jest", "pytest",
        "cypress", "selenium", "playwright", "k6", "locust", "sonarqube",
    ],
    "concept": [
        "rest api", "graphql", "grpc", "websocket", "microservices", "monolith",
        "event-driven", "cqrs", "ddd", "tdd", "bdd", "agile", "scrum", "kanban",
        "ci/cd", "devops", "mlops", "llmops", "rag", "vector search",
        "machine learning", "deep learning", "nlp", "computer vision", "llm",
        "data science", "data engineering", "etl", "elt", "data pipeline",
        "system design", "distributed systems", "concurrency", "multithreading",
        "oauth", "jwt", "rbac", "oauth2", "openid", "saml", "ssl", "tls",
    ],
    "soft": [
        "leadership", "communication", "teamwork", "problem solving", "critical thinking",
        "time management", "adaptability", "creativity", "collaboration", "mentoring",
        "project management", "stakeholder management", "conflict resolution",
        "presentation", "analytical", "attention to detail", "self-motivated",
    ],
}

# Flatten for quick lookup
ALL_SKILLS: set[str] = {s.lower() for skills in SKILL_TAXONOMY.values() for s in skills}

# Known certification patterns
CERT_PATTERNS: list[tuple[str, str]] = [
    (r"AWS\s+Certified\s+[\w\s]+",                        "AWS"),
    (r"Google\s+(?:Cloud\s+)?(?:Professional\s+)?[\w\s]+Certification", "Google Cloud"),
    (r"Microsoft\s+(?:Azure\s+)?(?:Certified|Associate|Expert)[\w\s]*", "Microsoft"),
    (r"Certified\s+Kubernetes\s+\w+\s*\(CK[AS]\)",       "CNCF"),
    (r"CKA|CKS|CKAD",                                     "CNCF"),
    (r"Certified\s+(?:Ethical\s+Hacker|Security|CISSP|CISM|CEH|CompTIA\s+\w+)", "Security"),
    (r"PMP|PMI[\-\s]\w+",                                 "PMI"),
    (r"Scrum\s+Master|CSM|PSM[\s\-]?\w*",                "Scrum"),
    (r"Deep\s+Learning\s+Specialization",                  "Coursera/DeepLearning.AI"),
    (r"TensorFlow\s+Developer\s+Certificate",              "Google"),
    (r"Oracle\s+Certified\s+[\w\s]+",                     "Oracle"),
    (r"Salesforce\s+Certified\s+[\w\s]+",                 "Salesforce"),
    (r"Cisco\s+(?:CCNA|CCNP|CCIE)[\w\s]*",               "Cisco"),
    (r"CompTIA\s+(?:A\+|Network\+|Security\+|CySA\+|CASP\+)", "CompTIA"),
    (r"RHCE|RHCSA",                                        "Red Hat"),
    (r"Databricks\s+Certified\s+[\w\s]+",                 "Databricks"),
    (r"Snowflake\s+[\w\s]+Certification",                  "Snowflake"),
]

# Degree keywords
DEGREE_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)\bph\.?d\.?\b|\bdoctor(?:ate)?\b",             "PhD"),
    (r"(?i)\bm\.?tech\.?\b|\bmaster(?:s)?\b|\bm\.?s\.?\b|\bm\.?e\.?\b|\bmba\b", "Masters"),
    (r"(?i)\bb\.?tech\.?\b|\bb\.?e\.?\b|\bbachelor(?:s)?\b|\bb\.?s\.?\b|\bb\.?sc\.?\b", "Bachelors"),
    (r"(?i)\bdiploma\b",                                   "Diploma"),
    (r"(?i)\basso?ciate(?:s)?\b",                          "Associate"),
]


@dataclass
class ExtractedEntities:
    contact:         dict[str, str]  = field(default_factory=dict)
    skills:          list[dict]      = field(default_factory=list)
    technical_skills: list[str]      = field(default_factory=list)
    soft_skills:     list[str]       = field(default_factory=list)
    certifications:  list[dict]      = field(default_factory=list)
    education_level: str             = "unknown"
    education_items: list[dict]      = field(default_factory=list)
    total_years_exp: float           = 0.0
    date_ranges:     list[str]       = field(default_factory=list)
    detected_seniority: str | None   = None


def extract_entities(text: str, sections: dict[str, str]) -> ExtractedEntities:
    result = ExtractedEntities()
    result.contact         = _extract_contact(text)
    result.skills          = _extract_skills(text)
    result.technical_skills = [s["name"] for s in result.skills if s["category"] != "soft"]
    result.soft_skills     = [s["name"] for s in result.skills if s["category"] == "soft"]
    result.certifications  = _extract_certifications(text)
    result.education_level, result.education_items = _extract_education(text, sections)
    result.date_ranges     = _extract_date_ranges(text)
    result.total_years_exp = _calculate_years_experience(result.date_ranges)
    result.detected_seniority = _detect_seniority(text, result.total_years_exp)
    return result


# ── Contact Extraction ────────────────────────────────────────────────────────
def _extract_contact(text: str) -> dict[str, str]:
    contact: dict[str, str] = {}

    email_m = re.search(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}", text)
    if email_m:
        contact["email"] = email_m.group()

    phone_m = re.search(
        r"(?:\+?91[\s\-]?)?(?:\+?1[\s\-]?)?[\(]?[6-9]\d{9}[\)]?"
        r"|(?:\+\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}",
        text
    )
    if phone_m:
        contact["phone"] = phone_m.group().strip()

    li_m = re.search(r"linkedin\.com/in/[\w\-]+", text, re.IGNORECASE)
    if li_m:
        contact["linkedin"] = "https://" + li_m.group()

    gh_m = re.search(r"github\.com/[\w\-]+", text, re.IGNORECASE)
    if gh_m:
        contact["github"] = "https://" + gh_m.group()

    web_m = re.search(
        r"https?://(?!linkedin|github)[\w\-]+\.[\w\-.]+(?:/[\w\-./?=&]*)?",
        text, re.IGNORECASE
    )
    if web_m:
        contact["website"] = web_m.group()

    # Name: heuristic — first non-empty line that has 2–4 words, no special chars
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        if re.match(r"^[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){1,3}$", line):
            contact["name"] = line
            break

    return contact


# ── Skill Extraction ──────────────────────────────────────────────────────────
def _extract_skills(text: str) -> list[dict]:
    text_lower = text.lower()
    found: list[dict] = []
    seen: set[str] = set()

    for category, skill_list in SKILL_TAXONOMY.items():
        for skill in skill_list:
            if skill in seen:
                continue
            # Match whole word / phrase
            pattern = r"(?<![a-zA-Z0-9+#])" + re.escape(skill) + r"(?![a-zA-Z0-9+#])"
            if re.search(pattern, text_lower):
                seen.add(skill)
                # Try to find proficiency nearby
                proficiency = _infer_proficiency(text_lower, skill)
                found.append({
                    "name":        skill.title() if len(skill) > 2 else skill.upper(),
                    "category":    category,
                    "proficiency": proficiency,
                })

    return found


def _infer_proficiency(text: str, skill: str) -> str:
    """Look for proficiency adjectives within 50 chars of the skill mention."""
    idx = text.find(skill)
    if idx == -1:
        return "intermediate"
    window = text[max(0, idx - 50): idx + 50]
    if re.search(r"\b(expert|proficient|advanced|strong|senior)\b", window):
        return "advanced"
    if re.search(r"\b(familiar|basic|beginner|learning|exposure)\b", window):
        return "beginner"
    return "intermediate"


# ── Certification Extraction ──────────────────────────────────────────────────
def _extract_certifications(text: str) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()

    for pattern, issuer in CERT_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            name = m.group().strip()
            if name in seen:
                continue
            seen.add(name)

            # Try to find a year near the match
            vicinity = text[max(0, m.start() - 100): m.end() + 100]
            year_m = re.search(r"\b(20\d{2})\b", vicinity)
            found.append({
                "name":   name,
                "issuer": issuer,
                "year":   int(year_m.group()) if year_m else None,
            })

    return found


# ── Education Extraction ──────────────────────────────────────────────────────
def _extract_education(text: str, sections: dict[str, str]) -> tuple[str, list[dict]]:
    edu_text = sections.get("education", text)
    level = "unknown"
    items: list[dict] = []

    for pattern, degree in DEGREE_PATTERNS:
        if re.search(pattern, edu_text):
            level = degree
            break

    # Extract institution lines (heuristic: Title Case lines in education section)
    for line in edu_text.split("\n"):
        line = line.strip()
        if len(line) > 8 and re.match(r"^[A-Z]", line):
            year_m = re.search(r"\b(19|20)\d{2}\b", line)
            items.append({
                "raw_line": line,
                "year":     int(year_m.group()) if year_m else None,
            })

    return level, items[:5]


# ── Date & Experience Calculation ─────────────────────────────────────────────
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def _extract_date_ranges(text: str) -> list[str]:
    pattern = (
        r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+)?"
        r"(?:19|20)\d{2}"
        r"\s*[-–—to]+\s*"
        r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+)?(?:(?:19|20)\d{2}|[Pp]resent|[Cc]urrent|[Nn]ow)"
    )
    return re.findall(pattern, text)


def _parse_date_str(s: str) -> datetime | None:
    """Convert 'Jan 2021' or '2021' or 'Present' → datetime."""
    s = s.strip()
    if re.match(r"(?i)present|current|now", s):
        return datetime.now()
    # "Month Year"
    m = re.match(r"(?i)([a-z]{3})\w*\.?\s+(20\d{2}|19\d{2})", s)
    if m:
        month = _MONTH_MAP.get(m.group(1).lower(), 1)
        return datetime(int(m.group(2)), month, 1)
    # "Year only"
    m = re.match(r"(20\d{2}|19\d{2})", s)
    if m:
        return datetime(int(m.group(1)), 1, 1)
    return None


def _calculate_years_experience(date_ranges: list[str]) -> float:
    total_days = 0
    sep_re = re.compile(r"\s*[-–—to]+\s*", re.IGNORECASE)

    for dr in date_ranges:
        parts = sep_re.split(dr, maxsplit=1)
        if len(parts) != 2:
            continue
        start = _parse_date_str(parts[0])
        end   = _parse_date_str(parts[1])
        if start and end and end >= start:
            total_days += (end - start).days

    years = round(total_days / 365.25, 1)
    return min(years, 40.0)  # sanity cap


def _detect_seniority(text: str, years: float) -> str:
    text_lower = text.lower()
    if re.search(r"\b(principal|staff|director|vp|vice president|head of|chief)\b", text_lower):
        return "Principal / Director"
    if re.search(r"\b(senior|sr\.?|lead|architect)\b", text_lower) or years >= 5:
        return "Senior"
    if re.search(r"\b(mid[\-\s]level|mid level)\b", text_lower) or 2 <= years < 5:
        return "Mid-Level"
    if re.search(r"\b(junior|jr\.?|associate|entry[\-\s]level|fresher|intern)\b", text_lower) or years < 2:
        return "Junior / Entry-Level"
    return "Mid-Level"
