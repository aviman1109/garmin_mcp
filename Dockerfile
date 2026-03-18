# ── Stage 1: base ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=38081 \
    MCP_TRANSPORT=http \
    MCP_PATH=/mcp

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip setuptools wheel hatchling && \
    pip install --no-cache-dir ".[test]"

RUN mkdir -p /data/tokens /app/config

# ── Stage 2: test ─────────────────────────────────────────────────────────
# config/accounts.yaml and data/tokens/ are gitignored local files present
# only on the NAS build host. secrets/ is excluded via .dockerignore.
# This stage is a local-only build artifact — never pushed to any registry.
#
# Usage:
#   docker build --target test .
FROM base AS test

COPY config ./config
COPY data /data
COPY tests ./tests

ENV GARMIN_ACCOUNTS_FILE=config/accounts.yaml

RUN pytest tests/ -v --tb=short

# ── Stage 3: production ───────────────────────────────────────────────────
# No credentials baked in.
# accounts.yaml and data/ are mounted as volumes at container runtime.
#
# Usage (default):
#   docker build -t garmin-mcp-new .
FROM base AS production

COPY config/accounts.example.yaml ./config/accounts.example.yaml
COPY tests ./tests

EXPOSE 38081

CMD ["garmin-multi-mcp"]
