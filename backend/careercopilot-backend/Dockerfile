
# Multi-stage Docker build for CareerCopilot AI

# ============================================
# Stage 1: Builder - Resolve and build dependencies
# ============================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install Poetry and its export plugin
RUN pip install --no-cache-dir poetry==2.4.1 poetry-plugin-export

# Copy dependency configuration
COPY pyproject.toml poetry.lock ./

# Copy README if it exists in the build context.
# If your pyproject declares README.md, that file must exist.
COPY README.md* ./

# Validate the lock file, export runtime dependencies, and build wheels
RUN poetry check --lock && \
    poetry export -f requirements.txt \
        --without-hashes \
        --only main \
        -o requirements.txt && \
    pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt


# ============================================
# Stage 2: Development - Local development with reload
# ============================================
FROM python:3.11-slim AS development

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies built in the builder stage
COPY --from=builder /wheels /wheels

RUN pip install --no-cache-dir --no-index \
        --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels

# Copy application source
COPY . .

EXPOSE 8000

# Development server with automatic reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "debug"]


# ============================================
# Stage 3: Production-oriented runtime
# ============================================
FROM python:3.11-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Create a non-root application user
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install runtime dependencies
COPY --from=builder /wheels /wheels

RUN pip install --no-cache-dir --no-index \
        --find-links=/wheels /wheels/*.whl && \
    rm -rf /wheels

# Copy source files with correct ownership
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8000

# Production-oriented server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "warning", "--no-access-log"]
