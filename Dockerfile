# Two-stage image (spec §4, §11). Stage 1 builds the SPA. Stage 2 runs
# `python -m heishamon_dashboard` (HTTP_PORT, STATIC_DIR). No Docker build is
# part of development validation; see the README release check.

# --- frontend ---------------------------------------------------------------
# Vite resolves `$catalog` to ../backend/heishamon_dashboard/catalog.json
# relative to frontend/vite.config.js, so the catalog is copied to that path
# in the build tree before `npm run build`.
# node:22-bookworm-slim
FROM node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS frontend

WORKDIR /src/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/index.html frontend/vite.config.js ./
COPY frontend/src ./src
COPY backend/heishamon_dashboard/catalog.json /src/backend/heishamon_dashboard/catalog.json
COPY backend/heishamon_dashboard/rules.json /src/backend/heishamon_dashboard/rules.json

ENV VITE_CACHE_DIR=/tmp/vite-docker
RUN npm run build

# --- runtime ----------------------------------------------------------------
# python:3.12-slim
FROM python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime

# ghcr.io/astral-sh/uv:0.12.24
COPY --from=ghcr.io/astral-sh/uv@sha256:3af4716e991d6956a41e573eab705d0ee08500cd829ed30293eb8472f372c65a /uv /uvx /bin/

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

# README.md is the project readme named by pyproject.toml. The directory COPY
# takes the whole package tree (subpackages, catalog.json, rules.json).
COPY README.md ./
COPY backend/heishamon_dashboard/ /app/backend/heishamon_dashboard/

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

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/system',timeout=3).status==200 else 1)"

# Exec form so Python is PID 1 and receives SIGTERM. Uvicorn's graceful
# shutdown (45 s) finishes the final flush inside compose's 60 s stop grace.
CMD ["python", "-m", "heishamon_dashboard"]
