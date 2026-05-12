# syntax=docker/dockerfile:1.7
# Multi-stage Dockerfile for the AgentGEOScore FastAPI backend.
#
# Build context is the repository root. The backend source lives in
# ``./backend``. We use ``uv`` for installing Python dependencies because
# it is significantly faster than pip and the project ships a
# ``uv.lock`` we want to honor.
#
# This image is consumed by Fly.io's GitHub-launch flow, by ``flyctl
# deploy``, and by local ``docker build`` for smoke-testing.

FROM python:3.14-slim AS builder

# --- System deps required to build the wheel ecosystem ----------------------
# ``lxml`` is the only C-extension in our stack that needs system libs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxslt1-dev \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install ``uv`` from the official static binary so the build is
# deterministic and does not depend on PyPI being online for uv itself.
COPY --from=ghcr.io/astral-sh/uv:0.4.30 /uv /usr/local/bin/uv

WORKDIR /app

# Copy lockfile + project metadata first so dependency installation is
# cached when only application source changes.
COPY backend/pyproject.toml backend/uv.lock backend/README.md* ./
COPY backend/app ./app
COPY backend/tests ./tests

# Sync dependencies into a project-local virtualenv.
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
RUN uv sync --frozen --no-dev --no-install-project \
    && uv pip install --no-deps .

# --- Runtime image ----------------------------------------------------------
FROM python:3.14-slim AS runtime

# Minimal runtime libs for ``lxml``.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the prepared virtualenv and source from the builder stage.
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

# Run as non-root for defense in depth.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080

EXPOSE 8080

# Use shell form so ``$PORT`` (set by Fly + Cloud Run) is honored. ``--proxy-headers``
# preserves the client IP through Fly's edge proxy.
CMD uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips="*"
