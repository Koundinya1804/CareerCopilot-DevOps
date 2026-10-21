"""
app/agents/role_skill_db.py
────────────────────────────
Role Skill Database for the Skill Gap Analyzer Agent.

Contains structured, weighted skill requirements for 6 target roles:
  - AI Engineer
  - ML Engineer
  - Data Scientist
  - Java Developer
  - Full Stack Developer
  - Cloud Engineer

Each role defines:
  - required_skills   : must-have skills with priority and min proficiency
  - preferred_skills  : nice-to-have skills
  - certifications    : recognised certifications that add value
  - tools             : day-to-day tooling knowledge
  - soft_skills       : behavioural competencies
  - salary_range_inr  : Indian market salary range (LPA)
  - career_path       : progression milestones
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Priority(str, Enum):
    CRITICAL = "critical"   # eliminates candidates if missing
    HIGH     = "high"       # strong differentiator
    MEDIUM   = "medium"     # nice-to-have, can be learned on the job
    LOW      = "low"        # bonus points


class Proficiency(str, Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    EXPERT       = "expert"


@dataclass(frozen=True)
class RoleSkill:
    name:            str
    priority:        Priority
    min_proficiency: Proficiency = Proficiency.INTERMEDIATE
    category:        str         = "technical"   # technical | tool | concept | soft
    description:     str         = ""            # Why this skill matters for the role
    learning_url:    str         = ""            # Canonical learning resource


@dataclass(frozen=True)
class RoleDefinition:
    key:              str
    title:            str
    icon:             str
    description:      str
    required_skills:  tuple[RoleSkill, ...]
    preferred_skills: tuple[RoleSkill, ...]
    certifications:   tuple[str, ...]
    tools:            tuple[str, ...]
    soft_skills:      tuple[str, ...]
    salary_range_inr: tuple[int, int]   # LPA
    avg_years_to_role: float
    career_path:      tuple[str, ...]


# ── Role Definitions ──────────────────────────────────────────────────────────

AI_ENGINEER = RoleDefinition(
    key="ai_engineer",
    title="AI Engineer",
    icon="🤖",
    description="Builds production AI systems using LLMs, RAG pipelines, and agent frameworks. Bridges ML research and software engineering.",
    salary_range_inr=(12, 40),
    avg_years_to_role=2.5,
    career_path=("Junior AI Engineer", "AI Engineer", "Senior AI Engineer", "Principal AI Architect", "Head of AI"),
    certifications=(
        "Google Cloud Professional ML Engineer",
        "AWS Machine Learning Specialty",
        "DeepLearning.AI LLMOps Specialization",
        "Databricks Certified Associate Developer for Apache Spark",
    ),
    tools=("LangChain", "LangGraph", "Hugging Face", "Weights & Biases", "MLflow",
           "FastAPI", "Docker", "Kubernetes", "Qdrant", "ChromaDB", "Redis"),
    soft_skills=("System thinking", "Technical communication", "Research mindset",
                 "Problem decomposition", "Stakeholder alignment"),
    required_skills=(
        RoleSkill("Python", Priority.CRITICAL, Proficiency.ADVANCED, "language",
                  "Primary language for all AI/ML workflows"),
        RoleSkill("Large Language Models (LLMs)", Priority.CRITICAL, Proficiency.INTERMEDIATE, "concept",
                  "Core building block — must understand prompting, fine-tuning, evaluation"),
        RoleSkill("RAG (Retrieval-Augmented Generation)", Priority.CRITICAL, Proficiency.INTERMEDIATE, "concept",
                  "Most common production AI pattern today"),
        RoleSkill("LangChain / LangGraph", Priority.HIGH, Proficiency.INTERMEDIATE, "framework",
                  "Standard orchestration framework for LLM apps"),
        RoleSkill("Vector Databases", Priority.HIGH, Proficiency.INTERMEDIATE, "concept",
                  "ChromaDB, Qdrant, Pinecone — required for RAG"),
        RoleSkill("Prompt Engineering", Priority.HIGH, Proficiency.ADVANCED, "concept",
                  "System prompts, few-shot, chain-of-thought, structured outputs"),
        RoleSkill("FastAPI", Priority.HIGH, Proficiency.INTERMEDIATE, "framework",
                  "Building AI microservices and APIs"),
        RoleSkill("REST API Design", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Docker", Priority.HIGH, Proficiency.INTERMEDIATE, "devops"),
        RoleSkill("Git", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("SQL", Priority.MEDIUM, Proficiency.INTERMEDIATE, "language"),
        RoleSkill("Embeddings & Semantic Search", Priority.CRITICAL, Proficiency.INTERMEDIATE, "concept",
                  "Sentence transformers, cosine similarity, HNSW indexes"),
        RoleSkill("PyTorch or TensorFlow", Priority.MEDIUM, Proficiency.BEGINNER, "framework",
                  "Understanding model architecture even if not building from scratch"),
        RoleSkill("Async Python (asyncio)", Priority.MEDIUM, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Linux / Bash", Priority.MEDIUM, Proficiency.INTERMEDIATE, "tool"),
    ),
    preferred_skills=(
        RoleSkill("Kubernetes", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("MLflow / Weights & Biases", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("Fine-tuning LLMs (LoRA, QLoRA)", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Agents & Tool Use", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Cloud (AWS / GCP / Azure)", Priority.MEDIUM, Proficiency.BEGINNER, "cloud"),
        RoleSkill("Redis", Priority.LOW, Proficiency.BEGINNER, "tool"),
        RoleSkill("Celery / Background Tasks", Priority.LOW, Proficiency.BEGINNER, "tool"),
        RoleSkill("TypeScript / React", Priority.LOW, Proficiency.BEGINNER, "language"),
    ),
)

ML_ENGINEER = RoleDefinition(
    key="ml_engineer",
    title="ML Engineer",
    icon="🧠",
    description="Builds, trains, deploys, and monitors machine learning models in production. Bridges data science research and production engineering.",
    salary_range_inr=(10, 35),
    avg_years_to_role=2.0,
    career_path=("Data Analyst", "Junior ML Engineer", "ML Engineer", "Senior ML Engineer", "Staff ML Engineer", "ML Architect"),
    certifications=(
        "AWS Machine Learning Specialty",
        "Google Cloud Professional ML Engineer",
        "TensorFlow Developer Certificate",
        "Deep Learning Specialization (Coursera/DeepLearning.AI)",
        "Databricks ML Professional",
    ),
    tools=("PyTorch", "TensorFlow", "scikit-learn", "MLflow", "Weights & Biases",
           "Apache Spark", "Airflow", "Docker", "Kubernetes", "SageMaker"),
    soft_skills=("Analytical thinking", "Experimentation mindset", "Statistical intuition",
                 "Collaboration with data scientists", "Production ownership"),
    required_skills=(
        RoleSkill("Python", Priority.CRITICAL, Proficiency.ADVANCED, "language"),
        RoleSkill("PyTorch", Priority.CRITICAL, Proficiency.INTERMEDIATE, "framework",
                  "Industry-standard deep learning framework"),
        RoleSkill("scikit-learn", Priority.CRITICAL, Proficiency.INTERMEDIATE, "framework",
                  "Classical ML — gradient boosting, SVMs, preprocessing"),
        RoleSkill("Machine Learning Fundamentals", Priority.CRITICAL, Proficiency.ADVANCED, "concept",
                  "Supervised/unsupervised, bias-variance, regularisation, evaluation metrics"),
        RoleSkill("SQL", Priority.HIGH, Proficiency.INTERMEDIATE, "language"),
        RoleSkill("NumPy / Pandas", Priority.CRITICAL, Proficiency.ADVANCED, "framework"),
        RoleSkill("Feature Engineering", Priority.HIGH, Proficiency.ADVANCED, "concept"),
        RoleSkill("Model Evaluation & Metrics", Priority.HIGH, Proficiency.ADVANCED, "concept",
                  "Precision, recall, AUC-ROC, RMSE, cross-validation"),
        RoleSkill("Docker", Priority.HIGH, Proficiency.INTERMEDIATE, "devops"),
        RoleSkill("MLflow / Experiment Tracking", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("Statistics & Probability", Priority.HIGH, Proficiency.ADVANCED, "concept"),
        RoleSkill("Deep Learning Architectures", Priority.HIGH, Proficiency.INTERMEDIATE, "concept",
                  "CNNs, RNNs, Transformers, attention mechanism"),
        RoleSkill("Git", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("REST API (model serving)", Priority.MEDIUM, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Linux / Bash", Priority.MEDIUM, Proficiency.INTERMEDIATE, "tool"),
    ),
    preferred_skills=(
        RoleSkill("NLP / Transformers", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Computer Vision", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Kubernetes", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("Apache Spark", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("Cloud ML Services (SageMaker / Vertex AI)", Priority.MEDIUM, Proficiency.BEGINNER, "cloud"),
        RoleSkill("LLM Fine-tuning", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Airflow / Pipeline Orchestration", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("TensorFlow", Priority.LOW, Proficiency.BEGINNER, "framework"),
    ),
)

DATA_SCIENTIST = RoleDefinition(
    key="data_scientist",
    title="Data Scientist",
    icon="📊",
    description="Extracts insights from data using statistics, machine learning, and visualisation. Drives data-informed decisions and builds predictive models.",
    salary_range_inr=(8, 28),
    avg_years_to_role=1.5,
    career_path=("Data Analyst", "Junior Data Scientist", "Data Scientist", "Senior Data Scientist", "Principal Data Scientist", "Head of Data Science"),
    certifications=(
        "IBM Data Science Professional Certificate",
        "Google Data Analytics Certificate",
        "Microsoft Certified: Azure Data Scientist Associate",
        "Certified Analytics Professional (CAP)",
        "Deep Learning Specialization",
    ),
    tools=("Jupyter", "Pandas", "scikit-learn", "Tableau", "Power BI",
           "Matplotlib", "Seaborn", "Plotly", "Snowflake", "dbt"),
    soft_skills=("Storytelling with data", "Business acumen", "Stakeholder communication",
                 "Hypothesis-driven thinking", "Presentation skills"),
    required_skills=(
        RoleSkill("Python", Priority.CRITICAL, Proficiency.ADVANCED, "language"),
        RoleSkill("Statistics & Probability", Priority.CRITICAL, Proficiency.ADVANCED, "concept",
                  "Hypothesis testing, distributions, A/B testing, regression analysis"),
        RoleSkill("Pandas / NumPy", Priority.CRITICAL, Proficiency.ADVANCED, "framework"),
        RoleSkill("Data Visualisation (Matplotlib/Seaborn/Plotly)", Priority.CRITICAL, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("SQL", Priority.CRITICAL, Proficiency.ADVANCED, "language",
                  "Complex queries, window functions, CTEs — used daily"),
        RoleSkill("Machine Learning (scikit-learn)", Priority.HIGH, Proficiency.INTERMEDIATE, "framework"),
        RoleSkill("Exploratory Data Analysis (EDA)", Priority.CRITICAL, Proficiency.ADVANCED, "concept"),
        RoleSkill("Feature Engineering", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("A/B Testing", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Jupyter Notebooks", Priority.HIGH, Proficiency.ADVANCED, "tool"),
        RoleSkill("Git", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("R (optional but valued)", Priority.LOW, Proficiency.BEGINNER, "language"),
        RoleSkill("Business Intelligence Tools (Tableau / Power BI)", Priority.MEDIUM, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("Data Cleaning & Preprocessing", Priority.CRITICAL, Proficiency.ADVANCED, "concept"),
    ),
    preferred_skills=(
        RoleSkill("Deep Learning / PyTorch", Priority.MEDIUM, Proficiency.BEGINNER, "framework"),
        RoleSkill("NLP / Text Analysis", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Cloud Data Platforms (BigQuery / Redshift)", Priority.MEDIUM, Proficiency.BEGINNER, "cloud"),
        RoleSkill("Apache Spark / PySpark", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("dbt (data build tool)", Priority.LOW, Proficiency.BEGINNER, "tool"),
        RoleSkill("Causal Inference", Priority.LOW, Proficiency.BEGINNER, "concept"),
        RoleSkill("Time Series Analysis", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Docker", Priority.LOW, Proficiency.BEGINNER, "devops"),
    ),
)

JAVA_DEVELOPER = RoleDefinition(
    key="java_developer",
    title="Java Developer",
    icon="☕",
    description="Builds enterprise-grade backend systems and microservices using Java ecosystem. Works on high-throughput, distributed applications.",
    salary_range_inr=(6, 25),
    avg_years_to_role=1.0,
    career_path=("Junior Java Developer", "Java Developer", "Senior Java Developer", "Java Architect", "Principal Engineer"),
    certifications=(
        "Oracle Certified Professional Java SE Developer",
        "Spring Professional Certification (VMware)",
        "AWS Developer Associate",
        "Oracle Certified Expert Java EE Developer",
    ),
    tools=("IntelliJ IDEA", "Maven", "Gradle", "JUnit", "Mockito",
           "SonarQube", "Jenkins", "Postman", "Jira"),
    soft_skills=("Attention to detail", "Code quality mindset", "Design thinking",
                 "Collaborative development", "Debugging discipline"),
    required_skills=(
        RoleSkill("Java (Core)", Priority.CRITICAL, Proficiency.ADVANCED, "language",
                  "OOP, generics, collections, exception handling, streams, lambdas"),
        RoleSkill("Spring Boot", Priority.CRITICAL, Proficiency.ADVANCED, "framework",
                  "The #1 Java framework for microservices — non-negotiable"),
        RoleSkill("Spring MVC / REST", Priority.CRITICAL, Proficiency.INTERMEDIATE, "framework"),
        RoleSkill("SQL / JDBC", Priority.CRITICAL, Proficiency.INTERMEDIATE, "language"),
        RoleSkill("JPA / Hibernate", Priority.HIGH, Proficiency.INTERMEDIATE, "framework",
                  "ORM — most Java apps use JPA for database access"),
        RoleSkill("Maven / Gradle", Priority.HIGH, Proficiency.INTERMEDIATE, "tool",
                  "Build tools — must know at least one"),
        RoleSkill("JUnit / Mockito (Testing)", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("Git", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("RESTful API Design", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Multithreading & Concurrency", Priority.HIGH, Proficiency.INTERMEDIATE, "concept",
                  "ExecutorService, synchronized, CompletableFuture"),
        RoleSkill("Design Patterns", Priority.HIGH, Proficiency.INTERMEDIATE, "concept",
                  "Singleton, Factory, Builder, Observer, Strategy"),
        RoleSkill("Docker", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("Linux / Bash", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("Microservices Architecture", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
    ),
    preferred_skills=(
        RoleSkill("Spring Security", Priority.MEDIUM, Proficiency.BEGINNER, "framework"),
        RoleSkill("Apache Kafka", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("Redis", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("Kubernetes", Priority.LOW, Proficiency.BEGINNER, "devops"),
        RoleSkill("GraphQL", Priority.LOW, Proficiency.BEGINNER, "concept"),
        RoleSkill("Cloud (AWS / GCP)", Priority.MEDIUM, Proficiency.BEGINNER, "cloud"),
        RoleSkill("Elasticsearch", Priority.LOW, Proficiency.BEGINNER, "tool"),
        RoleSkill("gRPC", Priority.LOW, Proficiency.BEGINNER, "concept"),
    ),
)

FULLSTACK_DEVELOPER = RoleDefinition(
    key="fullstack_developer",
    title="Full Stack Developer",
    icon="🌐",
    description="Builds complete web applications covering both frontend (React/Next.js) and backend (Node.js/Python). Ships end-to-end product features independently.",
    salary_range_inr=(6, 22),
    avg_years_to_role=1.5,
    career_path=("Junior Developer", "Full Stack Developer", "Senior Full Stack Developer", "Lead Engineer", "Engineering Manager"),
    certifications=(
        "AWS Developer Associate",
        "Meta Front-End Developer Certificate",
        "MongoDB Developer Associate",
        "Google UX Design Certificate",
    ),
    tools=("VS Code", "Postman", "Figma", "Chrome DevTools", "npm/yarn",
           "Webpack / Vite", "ESLint", "Jest", "GitHub Actions"),
    soft_skills=("Product thinking", "User empathy", "Collaboration", "Self-management",
                 "Rapid prototyping mindset"),
    required_skills=(
        RoleSkill("JavaScript (ES6+)", Priority.CRITICAL, Proficiency.ADVANCED, "language"),
        RoleSkill("TypeScript", Priority.HIGH, Proficiency.INTERMEDIATE, "language"),
        RoleSkill("React.js", Priority.CRITICAL, Proficiency.ADVANCED, "framework",
                  "Hooks, state management, routing, performance"),
        RoleSkill("Node.js", Priority.CRITICAL, Proficiency.INTERMEDIATE, "framework"),
        RoleSkill("REST API Design", Priority.CRITICAL, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("HTML5 / CSS3", Priority.CRITICAL, Proficiency.ADVANCED, "language"),
        RoleSkill("SQL", Priority.HIGH, Proficiency.INTERMEDIATE, "language"),
        RoleSkill("Git", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("Responsive Design / Tailwind CSS", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Authentication (JWT / OAuth2)", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("Database (PostgreSQL / MongoDB)", Priority.HIGH, Proficiency.INTERMEDIATE, "database"),
        RoleSkill("Docker", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("Testing (Jest / React Testing Library)", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("Express.js / Fastify", Priority.HIGH, Proficiency.INTERMEDIATE, "framework"),
    ),
    preferred_skills=(
        RoleSkill("Next.js", Priority.HIGH, Proficiency.INTERMEDIATE, "framework"),
        RoleSkill("GraphQL", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Redis", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("WebSockets", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Cloud (AWS / Vercel / Netlify)", Priority.MEDIUM, Proficiency.BEGINNER, "cloud"),
        RoleSkill("CI/CD (GitHub Actions)", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("Kubernetes", Priority.LOW, Proficiency.BEGINNER, "devops"),
        RoleSkill("Python (FastAPI / Django)", Priority.LOW, Proficiency.BEGINNER, "language"),
    ),
)

CLOUD_ENGINEER = RoleDefinition(
    key="cloud_engineer",
    title="Cloud Engineer",
    icon="☁️",
    description="Designs, implements, and manages cloud infrastructure. Enables scalable, secure, and highly available systems using AWS, GCP, or Azure.",
    salary_range_inr=(8, 30),
    avg_years_to_role=2.0,
    career_path=("System Administrator", "Cloud Engineer", "Senior Cloud Engineer", "Cloud Architect", "Principal Architect"),
    certifications=(
        "AWS Solutions Architect Associate",
        "AWS DevOps Engineer Professional",
        "Google Cloud Professional Cloud Architect",
        "Microsoft Azure Administrator (AZ-104)",
        "Certified Kubernetes Administrator (CKA)",
        "HashiCorp Terraform Associate",
    ),
    tools=("Terraform", "Ansible", "AWS CLI", "kubectl", "Helm",
           "Prometheus", "Grafana", "Jenkins", "GitHub Actions"),
    soft_skills=("Operational excellence", "Incident management", "Cost optimisation mindset",
                 "Documentation discipline", "On-call readiness"),
    required_skills=(
        RoleSkill("AWS / GCP / Azure", Priority.CRITICAL, Proficiency.ADVANCED, "cloud",
                  "Deep knowledge of at least one major cloud — EC2, S3, VPC, IAM, RDS, Lambda"),
        RoleSkill("Terraform (IaC)", Priority.CRITICAL, Proficiency.INTERMEDIATE, "devops",
                  "Industry standard Infrastructure-as-Code — most job descriptions require it"),
        RoleSkill("Docker", Priority.CRITICAL, Proficiency.ADVANCED, "devops"),
        RoleSkill("Kubernetes", Priority.CRITICAL, Proficiency.INTERMEDIATE, "devops",
                  "Container orchestration — EKS/GKE/AKS"),
        RoleSkill("Linux / Bash Scripting", Priority.CRITICAL, Proficiency.ADVANCED, "tool"),
        RoleSkill("Networking (VPC, Subnets, Security Groups, NAT)", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("CI/CD Pipelines (GitHub Actions / Jenkins)", Priority.HIGH, Proficiency.INTERMEDIATE, "devops"),
        RoleSkill("Monitoring (Prometheus / Grafana / CloudWatch)", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("IAM & Security", Priority.HIGH, Proficiency.INTERMEDIATE, "concept",
                  "Least-privilege, roles, policies, service accounts"),
        RoleSkill("Git", Priority.HIGH, Proficiency.INTERMEDIATE, "tool"),
        RoleSkill("Python / Bash (Automation)", Priority.HIGH, Proficiency.INTERMEDIATE, "language"),
        RoleSkill("Helm Charts", Priority.MEDIUM, Proficiency.INTERMEDIATE, "devops"),
        RoleSkill("Load Balancing & Auto-scaling", Priority.HIGH, Proficiency.INTERMEDIATE, "concept"),
        RoleSkill("S3 / Object Storage", Priority.HIGH, Proficiency.INTERMEDIATE, "cloud"),
    ),
    preferred_skills=(
        RoleSkill("Ansible / Chef / Puppet", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("Service Mesh (Istio / Linkerd)", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("ArgoCD / GitOps", Priority.MEDIUM, Proficiency.BEGINNER, "devops"),
        RoleSkill("Serverless (Lambda / Cloud Functions)", Priority.MEDIUM, Proficiency.INTERMEDIATE, "cloud"),
        RoleSkill("ELK Stack / Loki", Priority.MEDIUM, Proficiency.BEGINNER, "tool"),
        RoleSkill("Cost Optimisation & FinOps", Priority.MEDIUM, Proficiency.BEGINNER, "concept"),
        RoleSkill("Multi-cloud Strategy", Priority.LOW, Proficiency.BEGINNER, "concept"),
        RoleSkill("Go (for cloud tooling)", Priority.LOW, Proficiency.BEGINNER, "language"),
    ),
)


# ── Registry ──────────────────────────────────────────────────────────────────
ROLE_REGISTRY: dict[str, RoleDefinition] = {
    "ai_engineer":         AI_ENGINEER,
    "ml_engineer":         ML_ENGINEER,
    "data_scientist":      DATA_SCIENTIST,
    "java_developer":      JAVA_DEVELOPER,
    "fullstack_developer": FULLSTACK_DEVELOPER,
    "cloud_engineer":      CLOUD_ENGINEER,
}

ROLE_DISPLAY_ORDER = [
    "ai_engineer", "ml_engineer", "data_scientist",
    "java_developer", "fullstack_developer", "cloud_engineer",
]


def get_role(key: str) -> RoleDefinition:
    if key not in ROLE_REGISTRY:
        raise ValueError(
            f"Unknown role '{key}'. Valid roles: {list(ROLE_REGISTRY)}"
        )
    return ROLE_REGISTRY[key]


def get_all_role_skills(key: str) -> list[RoleSkill]:
    """Return all skills (required + preferred) for a role."""
    role = get_role(key)
    return list(role.required_skills) + list(role.preferred_skills)


def get_skill_names(key: str, required_only: bool = False) -> set[str]:
    """Return lowercase skill names for quick lookup."""
    role = get_role(key)
    names = {s.name.lower() for s in role.required_skills}
    if not required_only:
        names |= {s.name.lower() for s in role.preferred_skills}
    return names
