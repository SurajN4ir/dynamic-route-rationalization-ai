# Build context is the repo root (docker-compose.yml sets it), because the
# dependency manifest (pyproject.toml) lives at the root by design - see
# docs/architecture/10-repository-structure.md.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir uv==0.11.*

WORKDIR /build
COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml

WORKDIR /app
COPY services/api/app ./app
COPY services/api/alembic ./alembic
COPY services/api/alembic.ini ./alembic.ini

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
