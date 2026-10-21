"""
app/models/__init__.py
Imports all models so Alembic autogenerate (and Base.metadata.create_all)
can discover them. Every ORM model MUST be imported here -- if it's missing,
its table silently never gets created in a fresh database.
"""
from app.models.user import User, UserProfile, UserSkill  # noqa: F401
from app.models.resume import Resume, CareerReport  # noqa: F401
from app.models.session import ChatSession, ChatMessage  # noqa: F401
from app.models.skill_gap import SkillGapReport  # noqa: F401
from app.models.career_recommendation import CareerRecommendationReport  # noqa: F401
from app.models.interview import InterviewSession, InterviewQuestion, InterviewReport  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.agent_log import AgentLog  # noqa: F401
