"""
app/core/config.py
──────────────────
Centralised application settings loaded from environment variables / .env file.
All settings are type-validated by Pydantic v2.  Import `settings` anywhere.
"""

from __future__ import annotations
from urllib.parse import quote_plus
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "CareerCopilot AI"
    APP_VERSION: str = "1.0.0"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ── Server ───────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1

    # ── Security ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = Field(..., min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── MySQL ────────────────────────────────────────────────────────────────
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "careercopilot"
    MYSQL_PASSWORD: str = Field(...)
    MYSQL_DATABASE: str = "careercopilot"
    MYSQL_POOL_SIZE: int = 10
    MYSQL_MAX_OVERFLOW: int = 20
    MYSQL_POOL_TIMEOUT: int = 30
    MYSQL_POOL_RECYCLE: int = 1800

    @computed_field
    @property
    def DATABASE_URL(self) -> str:  # noqa: N802
        password = quote_plus(self.MYSQL_PASSWORD)
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{password}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            f"?charset=utf8mb4"
        )

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0

    @computed_field  # type: ignore[misc]
    @property
    def REDIS_URL(self) -> str:  # noqa: N802
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ── AWS / S3 ─────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"
    S3_BUCKET_NAME: str = "careercopilot-files"
    S3_ENDPOINT_URL: str | None = None  # MinIO override

    # ── LLM Providers ────────────────────────────────────────────────────────
    # Groq (default provider)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Google Gemini (fallback)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Anthropic (fallback)
    ANTHROPIC_API_KEY: str = ""

    # OpenAI (fallback)
    OPENAI_API_KEY: str = ""

    # Active provider selection — change to "gemini", "anthropic", or "openai" as needed
    DEFAULT_LLM_PROVIDER: str = "groq"
    DEFAULT_LLM_MODEL: str = "llama-3.3-70b-versatile"

    # ── Email ────────────────────────────────────────────────────────────────
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = True
    EMAIL_FROM: str = "CareerCopilot AI <noreply@careercopilot.ai>"

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:5173"
    ALLOWED_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    ALLOWED_HEADERS: str = "*"

    @computed_field  # type: ignore[misc]
    @property
    def CORS_ORIGINS(self) -> list[str]:  # noqa: N802
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_AGENT_PER_MINUTE: int = 10

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    # ── RAG Pipeline ──────────────────────────────────────────────────────────
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    CHROMA_COLLECTION_PREFIX: str = "careercopilot"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    RAG_TOP_K: int = 5
    RAG_SCORE_THRESHOLD: float = 0.30
    MAX_CONTEXT_TOKENS: int = 6000
    KNOWLEDGE_BASE_DIR: str = "./app/rag/knowledge_base"

    # ── Resume Analyzer ───────────────────────────────────────────────────────
    MAX_RESUME_SIZE_MB: int = 10
    ALLOWED_RESUME_TYPES: str = (
        "application/pdf,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    @computed_field  # type: ignore[misc]
    @property
    def MAX_RESUME_SIZE_BYTES(self) -> int:  # noqa: N802
        return self.MAX_RESUME_SIZE_MB * 1024 * 1024

    # ── Convenience: active model name for logging ─────────────────────────────
    @property
    def active_model(self) -> str:
        """Return the model name for the currently configured provider."""
        provider = self.DEFAULT_LLM_PROVIDER.lower()
        if provider == "groq":
            return self.GROQ_MODEL
        if provider == "gemini":
            return self.GEMINI_MODEL
        if provider == "anthropic":
            return self.ANTHROPIC_API_KEY and "claude-3-5-sonnet-20241022" or self.DEFAULT_LLM_MODEL
        if provider == "openai":
            return self.DEFAULT_LLM_MODEL
        return self.DEFAULT_LLM_MODEL


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance (singleton)."""
    return Settings()  # type: ignore[call-arg]


settings: Settings = get_settings()
