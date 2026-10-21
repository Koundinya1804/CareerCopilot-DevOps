"""app/api/v1/router.py"""
from fastapi import APIRouter
from app.api.v1.endpoints.auth                  import router as auth_router
from app.api.v1.endpoints.health                import router as health_router
from app.api.v1.endpoints.users                 import router as users_router
from app.api.v1.endpoints.resume                import router as resume_router
from app.api.v1.endpoints.rag                   import router as rag_router
from app.api.v1.endpoints.skill_gap             import router as skill_gap_router
from app.api.v1.endpoints.career_recommendation import router as career_rec_router
from app.api.v1.endpoints.interview             import router as interview_router
from app.api.v1.endpoints.admin                 import router as admin_router
from app.api.v1.endpoints.admin_extended        import router as admin_extended_router
from app.api.v1.endpoints.notifications         import router as notifications_router
from app.api.v1.endpoints.agent_chat import router as agent_chat_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health_router)
api_v1_router.include_router(auth_router)
api_v1_router.include_router(users_router)
api_v1_router.include_router(resume_router)
api_v1_router.include_router(rag_router)
api_v1_router.include_router(skill_gap_router)
api_v1_router.include_router(career_rec_router)
api_v1_router.include_router(interview_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(admin_extended_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(agent_chat_router)
