FROM node:22-slim AS web
WORKDIR /web
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS deps
RUN pip install --no-cache-dir uv==0.13.4
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Runtime image gets the finished venv only; uv and pip's build tooling stay in the deps stage.
FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
WORKDIR /srv
COPY --from=deps /srv/.venv .venv
COPY app/ app/
COPY packs/ packs/
COPY data/ data/
COPY --from=web /web/dist frontend/dist
ENV PATH=/srv/.venv/bin:$PATH PORT=8080
# Runs as a non-root user: anything the app writes at runtime goes to a mounted volume or /tmp.
USER 10001
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/api/health', timeout=2)"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
