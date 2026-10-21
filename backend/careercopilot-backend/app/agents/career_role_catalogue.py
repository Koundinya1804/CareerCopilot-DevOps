"""
app/agents/career_role_catalogue.py
─────────────────────────────────────
Comprehensive career role catalogue used by the recommendation engine.

Covers 20 roles across 6 domains:
  - AI / ML
  - Software Engineering
  - Data
  - Cloud / DevOps
  - Product / Management
  - Specialised Tech

Each role carries:
  - Weighted skill affinities (which skills strongly indicate fit)
  - Interest keywords (what people who enjoy this role care about)
  - Salary bands for India and global
  - Growth trajectory (YoY demand, 5-year outlook)
  - Education requirements
  - Personality traits that thrive
  - Related roles (for career pivots)
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CareerRole:
    key:          str
    title:        str
    domain:       str
    icon:         str
    tagline:      str

    # ── Scoring signals ────────────────────────────────────────────────────────
    # Skill keywords that, if present, boost this role's suitability score
    skill_keywords:    tuple[str, ...]
    # Interest keywords that, if mentioned, indicate this role
    interest_keywords: tuple[str, ...]
    # Personality traits that thrive in this role
    personality_traits: tuple[str, ...]

    # ── Weights (sum should be 100) ────────────────────────────────────────────
    skill_weight:      float = 50.0   # % of score from skills
    interest_weight:   float = 30.0   # % from interests
    experience_weight: float = 20.0   # % from years of experience match

    # ── Experience bands ───────────────────────────────────────────────────────
    min_years:    float = 0.0
    ideal_years:  float = 2.0
    senior_years: float = 5.0

    # ── Salary data (India, in LPA) ────────────────────────────────────────────
    salary_fresher_inr:  tuple[float, float] = (4.0,  8.0)
    salary_mid_inr:      tuple[float, float] = (8.0,  18.0)
    salary_senior_inr:   tuple[float, float] = (18.0, 40.0)

    # ── Global salary (USD / year) ─────────────────────────────────────────────
    salary_global_usd:   tuple[int, int]  = (60000, 130000)

    # ── Market data ────────────────────────────────────────────────────────────
    demand_growth_pct:   float = 15.0      # YoY job posting growth
    five_year_outlook:   str   = "growing"  # growing | stable | declining | booming
    remote_friendly:     bool  = True
    top_companies:       tuple[str, ...] = ()
    related_roles:       tuple[str, ...] = ()

    # ── Education ─────────────────────────────────────────────────────────────
    min_education:       str = "Bachelors"
    preferred_education: str = "Bachelors"


# ── Role Definitions ──────────────────────────────────────────────────────────

ROLES: dict[str, CareerRole] = {

    # ───────────── AI / ML DOMAIN ─────────────────────────────────────────────
    "ai_engineer": CareerRole(
        key="ai_engineer", title="AI Engineer", domain="AI/ML", icon="🤖",
        tagline="Build intelligent systems using LLMs, RAG, and agent frameworks",
        skill_keywords=(
            "python", "llm", "langchain", "langgraph", "rag", "vector database",
            "chromadb", "qdrant", "pinecone", "prompt engineering", "fastapi",
            "embeddings", "semantic search", "gemini", "openai", "anthropic",
            "hugging face", "transformers", "agents", "tool use", "fine-tuning",
            "docker", "rest api", "async", "redis",
        ),
        interest_keywords=(
            "artificial intelligence", "llm", "chatbot", "ai product", "generative ai",
            "automation", "natural language", "intelligent system", "ai application",
            "production ai", "ai infrastructure",
        ),
        personality_traits=("curious", "systems thinker", "product oriented", "pragmatic"),
        salary_fresher_inr=(8.0, 15.0), salary_mid_inr=(15.0, 30.0),
        salary_senior_inr=(30.0, 60.0), salary_global_usd=(90000, 200000),
        demand_growth_pct=85.0, five_year_outlook="booming",
        top_companies=("Google", "Anthropic", "OpenAI", "Microsoft", "Flipkart", "Swiggy"),
        related_roles=("ml_engineer", "backend_engineer", "data_scientist"),
    ),

    "ml_engineer": CareerRole(
        key="ml_engineer", title="ML Engineer", domain="AI/ML", icon="🧠",
        tagline="Train, deploy, and maintain production ML models at scale",
        skill_keywords=(
            "python", "pytorch", "tensorflow", "scikit-learn", "mlflow",
            "feature engineering", "model deployment", "kubernetes", "airflow",
            "spark", "pandas", "numpy", "statistics", "deep learning",
            "sagemaker", "vertex ai", "mlops", "docker", "sql",
        ),
        interest_keywords=(
            "machine learning", "model training", "deep learning", "data pipeline",
            "mlops", "model serving", "recommendation system", "prediction",
            "neural network", "research",
        ),
        personality_traits=("analytical", "methodical", "research oriented", "detail focused"),
        salary_fresher_inr=(7.0, 13.0), salary_mid_inr=(13.0, 28.0),
        salary_senior_inr=(28.0, 55.0), salary_global_usd=(85000, 180000),
        demand_growth_pct=40.0, five_year_outlook="booming",
        top_companies=("Google", "Meta", "Netflix", "Uber", "Zomato"),
        related_roles=("ai_engineer", "data_scientist", "data_engineer"),
    ),

    "data_scientist": CareerRole(
        key="data_scientist", title="Data Scientist", domain="AI/ML", icon="📊",
        tagline="Extract insights and build predictive models from complex datasets",
        skill_keywords=(
            "python", "pandas", "numpy", "scikit-learn", "sql", "statistics",
            "matplotlib", "seaborn", "tableau", "r", "hypothesis testing",
            "a/b testing", "jupyter", "regression", "classification", "clustering",
            "feature engineering", "data visualisation", "power bi",
        ),
        interest_keywords=(
            "data analysis", "statistics", "business intelligence", "insights",
            "visualisation", "experiment design", "research", "analytics",
            "data storytelling", "dashboards",
        ),
        personality_traits=("inquisitive", "statistical thinker", "communicator", "business minded"),
        salary_fresher_inr=(5.0, 10.0), salary_mid_inr=(10.0, 22.0),
        salary_senior_inr=(22.0, 45.0), salary_global_usd=(75000, 160000),
        demand_growth_pct=30.0, five_year_outlook="growing",
        top_companies=("Amazon", "IBM", "Accenture", "Fractal", "Tiger Analytics"),
        related_roles=("ml_engineer", "data_engineer", "business_analyst"),
    ),

    # ───────────── SOFTWARE ENGINEERING ───────────────────────────────────────
    "backend_engineer": CareerRole(
        key="backend_engineer", title="Backend Engineer", domain="Software Engineering", icon="⚙️",
        tagline="Design scalable APIs, services, and data systems that power applications",
        skill_keywords=(
            "python", "java", "go", "nodejs", "fastapi", "spring boot", "django",
            "rest api", "grpc", "microservices", "postgresql", "mongodb",
            "redis", "kafka", "docker", "kubernetes", "sql", "system design",
            "caching", "message queue", "authentication",
        ),
        interest_keywords=(
            "system design", "api design", "scalability", "performance", "backend",
            "distributed systems", "microservices", "server side", "database design",
        ),
        personality_traits=("systematic", "performance minded", "reliability focused", "problem solver"),
        salary_fresher_inr=(5.0, 10.0), salary_mid_inr=(10.0, 25.0),
        salary_senior_inr=(25.0, 50.0), salary_global_usd=(80000, 170000),
        demand_growth_pct=20.0, five_year_outlook="growing",
        top_companies=("Google", "Amazon", "Flipkart", "Razorpay", "CRED"),
        related_roles=("fullstack_engineer", "devops_engineer", "data_engineer"),
    ),

    "fullstack_engineer": CareerRole(
        key="fullstack_engineer", title="Full Stack Engineer", domain="Software Engineering", icon="🌐",
        tagline="Build complete web products from pixel-perfect UIs to scalable backends",
        skill_keywords=(
            "javascript", "typescript", "react", "nextjs", "nodejs", "express",
            "html", "css", "tailwind", "rest api", "postgresql", "mongodb",
            "git", "docker", "jwt", "oauth", "testing", "ci/cd",
        ),
        interest_keywords=(
            "web development", "product", "frontend", "backend", "startup",
            "user experience", "full product", "building apps", "saas",
        ),
        personality_traits=("versatile", "product oriented", "independent", "fast learner"),
        salary_fresher_inr=(4.0, 9.0), salary_mid_inr=(9.0, 22.0),
        salary_senior_inr=(22.0, 45.0), salary_global_usd=(70000, 150000),
        demand_growth_pct=22.0, five_year_outlook="growing",
        top_companies=("Startups", "Razorpay", "Freshworks", "Zoho", "Browserstack"),
        related_roles=("backend_engineer", "frontend_engineer", "mobile_engineer"),
    ),

    "frontend_engineer": CareerRole(
        key="frontend_engineer", title="Frontend Engineer", domain="Software Engineering", icon="🎨",
        tagline="Craft fast, accessible, and delightful user interfaces",
        skill_keywords=(
            "javascript", "typescript", "react", "vue", "angular", "nextjs",
            "html5", "css3", "tailwind", "figma", "accessibility", "performance",
            "webpack", "vite", "testing", "jest", "storybook",
        ),
        interest_keywords=(
            "ui design", "user experience", "animations", "accessibility",
            "visual design", "web performance", "component library",
        ),
        personality_traits=("detail oriented", "design sensibility", "empathetic", "creative"),
        salary_fresher_inr=(4.0, 8.0), salary_mid_inr=(8.0, 18.0),
        salary_senior_inr=(18.0, 35.0), salary_global_usd=(65000, 140000),
        demand_growth_pct=18.0, five_year_outlook="stable",
        top_companies=("Atlassian", "Figma", "Clevertap", "Browserstack"),
        related_roles=("fullstack_engineer", "mobile_engineer", "ui_ux_designer"),
    ),

    "mobile_engineer": CareerRole(
        key="mobile_engineer", title="Mobile Engineer", domain="Software Engineering", icon="📱",
        tagline="Build native and cross-platform mobile apps used by millions",
        skill_keywords=(
            "react native", "flutter", "swift", "kotlin", "ios", "android",
            "dart", "xcode", "android studio", "rest api", "firebase",
            "push notifications", "offline storage",
        ),
        interest_keywords=(
            "mobile apps", "ios", "android", "cross-platform", "app store",
            "consumer apps", "mobile ux",
        ),
        personality_traits=("performance aware", "UX focused", "platform expert"),
        salary_fresher_inr=(5.0, 10.0), salary_mid_inr=(10.0, 22.0),
        salary_senior_inr=(22.0, 42.0), salary_global_usd=(75000, 155000),
        demand_growth_pct=15.0, five_year_outlook="stable",
        top_companies=("BYJU'S", "Meesho", "Dream11", "PhonePe"),
        related_roles=("frontend_engineer", "fullstack_engineer"),
    ),

    "java_developer": CareerRole(
        key="java_developer", title="Java Developer", domain="Software Engineering", icon="☕",
        tagline="Build enterprise-grade backend systems with the Java ecosystem",
        skill_keywords=(
            "java", "spring boot", "spring mvc", "jpa", "hibernate",
            "maven", "gradle", "junit", "microservices", "rest api",
            "sql", "docker", "design patterns", "multithreading",
            "concurrency", "kafka",
        ),
        interest_keywords=(
            "enterprise software", "java ecosystem", "backend", "banking tech",
            "fintech", "large-scale systems", "reliability",
        ),
        personality_traits=("rigorous", "structured", "quality focused", "patient"),
        salary_fresher_inr=(4.0, 9.0), salary_mid_inr=(9.0, 20.0),
        salary_senior_inr=(20.0, 40.0), salary_global_usd=(70000, 145000),
        demand_growth_pct=10.0, five_year_outlook="stable",
        top_companies=("TCS", "Infosys", "Goldman Sachs", "JP Morgan", "PhonePe"),
        related_roles=("backend_engineer", "fullstack_engineer"),
    ),

    # ───────────── DATA DOMAIN ─────────────────────────────────────────────────
    "data_engineer": CareerRole(
        key="data_engineer", title="Data Engineer", domain="Data", icon="🔧",
        tagline="Build pipelines that power analytics, ML, and business decisions",
        skill_keywords=(
            "python", "spark", "kafka", "airflow", "sql", "dbt",
            "bigquery", "redshift", "snowflake", "hadoop", "hive",
            "etl", "data pipeline", "docker", "aws", "data warehouse",
        ),
        interest_keywords=(
            "data pipeline", "etl", "data warehouse", "big data", "streaming",
            "data infrastructure", "batch processing", "data quality",
        ),
        personality_traits=("methodical", "scalability focused", "infrastructure minded"),
        salary_fresher_inr=(6.0, 11.0), salary_mid_inr=(11.0, 25.0),
        salary_senior_inr=(25.0, 50.0), salary_global_usd=(80000, 165000),
        demand_growth_pct=35.0, five_year_outlook="booming",
        top_companies=("Databricks", "Airtel", "Swiggy", "Dunzo", "Lenskart"),
        related_roles=("data_scientist", "ml_engineer", "backend_engineer"),
    ),

    "business_analyst": CareerRole(
        key="business_analyst", title="Business Analyst", domain="Data", icon="📈",
        tagline="Bridge business strategy and technology through data-driven insights",
        skill_keywords=(
            "sql", "excel", "tableau", "power bi", "python", "data analysis",
            "requirements gathering", "stakeholder management", "user stories",
            "process mapping",
        ),
        interest_keywords=(
            "business strategy", "process improvement", "stakeholders", "requirements",
            "analytics", "consulting", "product analysis",
        ),
        personality_traits=("communicative", "analytical", "strategic", "collaborative"),
        salary_fresher_inr=(4.0, 8.0), salary_mid_inr=(8.0, 18.0),
        salary_senior_inr=(18.0, 35.0), salary_global_usd=(60000, 120000),
        demand_growth_pct=12.0, five_year_outlook="stable",
        top_companies=("Deloitte", "McKinsey", "Accenture", "Amazon"),
        related_roles=("data_scientist", "product_manager"),
    ),

    # ───────────── CLOUD / DEVOPS ──────────────────────────────────────────────
    "cloud_engineer": CareerRole(
        key="cloud_engineer", title="Cloud Engineer", domain="Cloud/DevOps", icon="☁️",
        tagline="Architect and manage cloud infrastructure for global scale",
        skill_keywords=(
            "aws", "gcp", "azure", "terraform", "docker", "kubernetes",
            "linux", "bash", "networking", "iam", "ci/cd", "monitoring",
            "prometheus", "grafana", "helm", "s3", "vpc", "load balancing",
        ),
        interest_keywords=(
            "cloud infrastructure", "devops", "site reliability", "aws",
            "infrastructure as code", "automation", "scalability",
        ),
        personality_traits=("operational excellence", "reliability focused", "automation lover"),
        salary_fresher_inr=(5.0, 11.0), salary_mid_inr=(11.0, 25.0),
        salary_senior_inr=(25.0, 50.0), salary_global_usd=(85000, 175000),
        demand_growth_pct=38.0, five_year_outlook="booming",
        top_companies=("AWS", "Google Cloud", "Microsoft", "HashiCorp", "Atlassian"),
        related_roles=("devops_engineer", "sre_engineer", "backend_engineer"),
    ),

    "devops_engineer": CareerRole(
        key="devops_engineer", title="DevOps Engineer", domain="Cloud/DevOps", icon="🔁",
        tagline="Accelerate software delivery through automation and reliable pipelines",
        skill_keywords=(
            "jenkins", "github actions", "gitlab ci", "docker", "kubernetes",
            "ansible", "terraform", "bash", "python", "linux",
            "monitoring", "prometheus", "elk", "git",
        ),
        interest_keywords=(
            "ci/cd", "automation", "deployment", "pipeline", "devops culture",
            "reliability", "developer productivity",
        ),
        personality_traits=("automation first", "collaborative", "reliability focused"),
        salary_fresher_inr=(5.0, 10.0), salary_mid_inr=(10.0, 22.0),
        salary_senior_inr=(22.0, 45.0), salary_global_usd=(80000, 160000),
        demand_growth_pct=28.0, five_year_outlook="growing",
        top_companies=("ThoughtWorks", "Razorpay", "Zepto", "Meesho"),
        related_roles=("cloud_engineer", "sre_engineer", "backend_engineer"),
    ),

    "sre_engineer": CareerRole(
        key="sre_engineer", title="Site Reliability Engineer", domain="Cloud/DevOps", icon="🛡️",
        tagline="Ensure production systems are reliable, scalable, and observable",
        skill_keywords=(
            "sre", "linux", "python", "go", "kubernetes", "prometheus",
            "grafana", "elk", "incident management", "slo", "sla",
            "chaos engineering", "monitoring", "alerting",
        ),
        interest_keywords=(
            "reliability", "on-call", "incident management", "observability",
            "capacity planning", "performance",
        ),
        personality_traits=("calm under pressure", "systematic", "root cause analyst"),
        salary_fresher_inr=(7.0, 13.0), salary_mid_inr=(13.0, 28.0),
        salary_senior_inr=(28.0, 55.0), salary_global_usd=(90000, 185000),
        demand_growth_pct=32.0, five_year_outlook="booming",
        top_companies=("Google", "Netflix", "Flipkart", "Ola"),
        related_roles=("cloud_engineer", "devops_engineer", "backend_engineer"),
    ),

    # ───────────── PRODUCT / MANAGEMENT ───────────────────────────────────────
    "product_manager": CareerRole(
        key="product_manager", title="Product Manager", domain="Product", icon="🎯",
        tagline="Define the product vision and drive cross-functional teams to ship",
        skill_keywords=(
            "product roadmap", "user research", "analytics", "sql",
            "agile", "scrum", "stakeholder management", "jira",
            "wireframing", "figma", "a/b testing", "metrics",
        ),
        interest_keywords=(
            "product strategy", "user experience", "business metrics", "roadmap",
            "growth", "market research", "leadership", "vision",
        ),
        personality_traits=("strategic", "empathetic", "communicative", "data driven"),
        salary_fresher_inr=(8.0, 15.0), salary_mid_inr=(15.0, 30.0),
        salary_senior_inr=(30.0, 60.0), salary_global_usd=(90000, 200000),
        demand_growth_pct=20.0, five_year_outlook="growing",
        top_companies=("Google", "Amazon", "Razorpay", "CRED", "Zepto"),
        related_roles=("business_analyst", "data_scientist", "engineering_manager"),
        preferred_education="MBA or Bachelors in CS",
    ),

    "engineering_manager": CareerRole(
        key="engineering_manager", title="Engineering Manager", domain="Product", icon="👥",
        tagline="Lead engineering teams to build great products with technical excellence",
        skill_keywords=(
            "leadership", "system design", "technical strategy", "agile",
            "python", "java", "backend", "hiring", "performance reviews",
            "roadmap", "stakeholder management",
        ),
        interest_keywords=(
            "team leadership", "mentoring", "engineering culture", "hiring",
            "management", "strategy", "people development",
        ),
        personality_traits=("empathetic leader", "strategic", "organized", "communicator"),
        salary_fresher_inr=(0, 0), salary_mid_inr=(25.0, 45.0),
        salary_senior_inr=(45.0, 80.0), salary_global_usd=(130000, 250000),
        demand_growth_pct=15.0, five_year_outlook="stable",
        min_years=6.0, ideal_years=8.0,
        top_companies=("FAANG", "Unicorn startups"),
        related_roles=("backend_engineer", "product_manager"),
    ),

    # ───────────── SPECIALISED TECH ───────────────────────────────────────────
    "cybersecurity_engineer": CareerRole(
        key="cybersecurity_engineer", title="Cybersecurity Engineer",
        domain="Specialised Tech", icon="🔒",
        tagline="Protect systems, data, and users from threats and vulnerabilities",
        skill_keywords=(
            "network security", "penetration testing", "ethical hacking",
            "linux", "python", "bash", "siem", "firewall", "owasp",
            "vulnerability assessment", "incident response", "cryptography",
        ),
        interest_keywords=(
            "security", "hacking", "ctf", "malware analysis", "cryptography",
            "privacy", "threat intelligence",
        ),
        personality_traits=("meticulous", "adversarial thinker", "detail oriented"),
        salary_fresher_inr=(5.0, 10.0), salary_mid_inr=(10.0, 22.0),
        salary_senior_inr=(22.0, 45.0), salary_global_usd=(80000, 170000),
        demand_growth_pct=33.0, five_year_outlook="booming",
        top_companies=("Palo Alto Networks", "IBM", "Deloitte", "Wipro"),
        related_roles=("cloud_engineer", "devops_engineer"),
    ),

    "blockchain_developer": CareerRole(
        key="blockchain_developer", title="Blockchain Developer",
        domain="Specialised Tech", icon="⛓️",
        tagline="Build decentralised applications and smart contracts on blockchain platforms",
        skill_keywords=(
            "solidity", "ethereum", "web3.js", "rust", "go", "javascript",
            "smart contracts", "defi", "nft", "truffle", "hardhat",
            "cryptography", "consensus mechanisms",
        ),
        interest_keywords=(
            "blockchain", "crypto", "defi", "web3", "smart contracts",
            "decentralisation", "nft", "dao",
        ),
        personality_traits=("innovator", "risk tolerant", "independent thinker"),
        salary_fresher_inr=(7.0, 14.0), salary_mid_inr=(14.0, 30.0),
        salary_senior_inr=(30.0, 60.0), salary_global_usd=(90000, 200000),
        demand_growth_pct=25.0, five_year_outlook="growing",
        top_companies=("Polygon", "Consensys", "CoinDCX", "WazirX"),
        related_roles=("backend_engineer", "ai_engineer"),
    ),

    "game_developer": CareerRole(
        key="game_developer", title="Game Developer", domain="Specialised Tech", icon="🎮",
        tagline="Create immersive games and interactive experiences",
        skill_keywords=(
            "unity", "unreal engine", "c#", "c++", "python", "game physics",
            "3d modelling", "opengl", "vulkan", "game design",
            "multiplayer", "shader", "vr", "ar",
        ),
        interest_keywords=(
            "gaming", "game design", "virtual reality", "interactive", "simulation",
            "3d graphics", "storytelling",
        ),
        personality_traits=("creative", "persistent", "detail oriented", "gamer"),
        salary_fresher_inr=(4.0, 8.0), salary_mid_inr=(8.0, 18.0),
        salary_senior_inr=(18.0, 35.0), salary_global_usd=(65000, 140000),
        demand_growth_pct=18.0, five_year_outlook="growing",
        top_companies=("Nazara", "PlaySimple", "Zynga", "Unity Technologies"),
        related_roles=("frontend_engineer", "mobile_engineer"),
    ),

    "ui_ux_designer": CareerRole(
        key="ui_ux_designer", title="UI/UX Designer", domain="Specialised Tech", icon="✏️",
        tagline="Design intuitive products that users love through research and creativity",
        skill_keywords=(
            "figma", "sketch", "adobe xd", "user research", "wireframing",
            "prototyping", "design system", "usability testing", "html", "css",
            "interaction design", "information architecture",
        ),
        interest_keywords=(
            "design", "user research", "visual design", "interaction", "prototyping",
            "design thinking", "accessibility", "brand",
        ),
        personality_traits=("empathetic", "creative", "communicative", "user advocate"),
        salary_fresher_inr=(4.0, 8.0), salary_mid_inr=(8.0, 18.0),
        salary_senior_inr=(18.0, 35.0), salary_global_usd=(60000, 130000),
        demand_growth_pct=20.0, five_year_outlook="growing",
        top_companies=("Clevertap", "Hotstar", "Razorpay", "Swiggy"),
        related_roles=("frontend_engineer", "product_manager"),
    ),

    "solutions_architect": CareerRole(
        key="solutions_architect", title="Solutions Architect",
        domain="Cloud/DevOps", icon="🏛️",
        tagline="Design end-to-end technical solutions that meet business requirements",
        skill_keywords=(
            "system design", "aws", "gcp", "azure", "microservices",
            "security", "networking", "databases", "apis",
            "solution design", "enterprise architecture", "cost optimisation",
        ),
        interest_keywords=(
            "architecture", "system design", "consulting", "enterprise",
            "technical leadership", "pre-sales",
        ),
        personality_traits=("holistic thinker", "communicative", "experienced", "strategic"),
        salary_fresher_inr=(0, 0), salary_mid_inr=(18.0, 35.0),
        salary_senior_inr=(35.0, 70.0), salary_global_usd=(100000, 210000),
        demand_growth_pct=25.0, five_year_outlook="growing",
        min_years=5.0, ideal_years=8.0,
        top_companies=("AWS", "Google", "Deloitte", "Infosys"),
        related_roles=("cloud_engineer", "backend_engineer", "engineering_manager"),
    ),
}

ROLE_DISPLAY_ORDER = [
    "ai_engineer", "ml_engineer", "data_scientist", "data_engineer",
    "backend_engineer", "fullstack_engineer", "frontend_engineer",
    "java_developer", "cloud_engineer", "devops_engineer", "sre_engineer",
    "mobile_engineer", "product_manager", "engineering_manager",
    "cybersecurity_engineer", "blockchain_developer", "game_developer",
    "ui_ux_designer", "solutions_architect", "business_analyst",
]


def get_career_role(key: str) -> CareerRole:
    if key not in ROLES:
        raise ValueError(f"Unknown career role '{key}'. Valid: {list(ROLES)}")
    return ROLES[key]
