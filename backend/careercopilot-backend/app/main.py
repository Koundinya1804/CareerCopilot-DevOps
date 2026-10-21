"""
app/main.py
───────────
FastAPI application factory for CareerCopilot AI.

Start the server:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Or via the helper script:
    python -m app.main
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.redis import check_redis_connection
from app.db.session import check_database_connection
from app.middleware.logging import RequestLoggingMiddleware

# Configure structured logging before anything else
configure_logging()
logger = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup checks; clean up on shutdown."""
    logger.info(
        "application_starting",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        env=settings.APP_ENV,
    )

    # Verify external dependencies are reachable
    check_database_connection()
    check_redis_connection()

    logger.info("application_ready")
    yield

    # Teardown
    logger.info("application_shutdown")


# ── Application Factory ───────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "Multi-Agent Career Guidance & Placement Preparation Platform. "
            "Powered by RAG, LLMs, and Agent Orchestration."
        ),
        docs_url="/docs"    if settings.is_development else None,
        redoc_url="/redoc"  if settings.is_development else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (outermost → innermost) ────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.add_middleware(RequestLoggingMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────────────
    register_exception_handlers(app)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(api_v1_router)

    # ── Root redirect ─────────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "app":     settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs":    "/docs" if settings.is_development else "disabled in production",
        }

    return app


app = create_app()


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_development,
        workers=1 if settings.is_development else settings.WORKERS,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=False,  # handled by our middleware
    )
