"""
app/db/session.py
─────────────────
SQLAlchemy 2.x synchronous session management for MySQL (PyMySQL driver).

Provides:
  - engine          : the SQLAlchemy Engine (connection pool)
  - SessionLocal    : session factory (use as context manager)
  - get_db()        : FastAPI dependency that yields a session and commits/
                      rolls back automatically
  - Base            : declarative base for all ORM models
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Declarative Base ──────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass


# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.MYSQL_POOL_SIZE,
    max_overflow=settings.MYSQL_MAX_OVERFLOW,
    pool_timeout=settings.MYSQL_POOL_TIMEOUT,
    pool_recycle=settings.MYSQL_POOL_RECYCLE,
    pool_pre_ping=True,           # verify connection health before checkout
    echo=settings.is_development, # log SQL in dev, silent in prod
    connect_args={
        "connect_timeout": 10,
        "charset": "utf8mb4",
    },
)


@event.listens_for(engine, "connect")
def _set_mysql_session_vars(dbapi_connection: object, connection_record: object) -> None:
    """Set MySQL session variables on every new connection."""
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
    cursor.execute("SET time_zone = '+00:00'")
    cursor.close()


# ── Session Factory ───────────────────────────────────────────────────────────
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,  # safe for async-style usage
)


# ── FastAPI Dependency ────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    Yield a database session; commit on success, rollback on exception.

    Usage in route:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...
    """
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ── Health Check ──────────────────────────────────────────────────────────────
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def check_database_connection() -> bool:
    """
    Verify database connectivity with retry logic.
    Called at application startup.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("db_connection_ok", host=settings.MYSQL_HOST, db=settings.MYSQL_DATABASE)
        return True
    except Exception as exc:
        logger.error("db_connection_failed", error=str(exc))
        raise
