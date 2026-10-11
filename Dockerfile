# Two-stage image (spec §4, §11). Stage 1 builds the SPA. Stage 2 runs
# `python -m heishamon_dashboard` (HTTP_PORT, STATIC_DIR). No Docker build is
# part of development validation; see the README release check.

# --- frontend ---------------------------------------------------------------
# Vite resolves `$catalog` to ../backend/heishamon_dashboard/catalog.json
# relative to frontend/vite.config.js, so the catalog is copied to that path
# in the build tree before `npm run build`.
FROM node:22-bookworm-slim AS frontend

WORKDIR /src/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
COPY backend/heishamon_dashboard/catalog.json /src/backend/heishamon_dashboard/catalog.json

ENV VITE_CACHE_DIR=/tmp/vite-docker
RUN npm run build

# --- runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin dashboard \
    && mkdir -p /data /app/static \
    && chown dashboard:dashboard /data

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PYTHON=3.12

# Dependencies from the lockfile only. The project wheel is installed after
# the sources are copied, so this layer stays cached when application code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# README.md is the project readme named by pyproject.toml. The package tree
# includes catalog.json next to the modules (loaded from the installed package).
COPY README.md ./
RUN mkdir -p /app/backend/heishamon_dashboard
COPY backend/heishamon_dashboard/*.py backend/heishamon_dashboard/catalog.json \
    /app/backend/heishamon_dashboard/

RUN uv sync --frozen --no-dev --no-editable \
    && /app/.venv/bin/python -c "from pathlib import Path; import heishamon_dashboard; p = Path(heishamon_dashboard.__file__).resolve().parent / 'catalog.json'; assert p.is_file(), p"

COPY --from=frontend --chown=dashboard:dashboard /src/frontend/dist /app/static

# Installed layout is not the repo tree, so the in-repo default
# `<repo>/frontend/dist` would miss. Point the process at the built SPA.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    STATIC_DIR=/app/static \
    HTTP_PORT=8000

VOLUME /data
EXPOSE 8000

USER dashboard

# Exec form so Python is PID 1 and receives SIGTERM. Uvicorn's graceful
# shutdown (45 s) finishes the final flush inside compose's 60 s stop grace.
CMD ["python", "-m", "heishamon_dashboard"]
