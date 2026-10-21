from app.db.session import Base, engine

# Import all models
from app.models.user import *
from app.models.resume import *
from app.models.interview import *
from app.models.session import *
from app.models.skill_gap import *
from app.models.career_recommendation import *
from app.models.notification import *
from app.models.agent_log import *

print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")
