FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=38081 \
    MCP_TRANSPORT=http \
    MCP_PATH=/mcp

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
COPY tests ./tests

RUN pip install --no-cache-dir --upgrade pip setuptools wheel hatchling && \
    pip install --no-cache-dir ".[test]"

RUN mkdir -p /data/tokens /app/config
# To run functional tests (requires valid tokens mounted):
#   docker exec <container> pytest tests/ -v

EXPOSE 38081

CMD ["garmin-multi-mcp"]
