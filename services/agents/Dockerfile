# Agent service image: the API, the worker, the bridge, the MCP server and the batch commands.
# Build from the repository root: docker build -f services/agents/Dockerfile -t tramita-agents .
# The code finds the catalog, the conditions and the evaluation sets relative to /app, so the
# repository layout is kept. Search models are not baked in: they are downloaded once into
# /models (a volume in Kubernetes).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version ./
COPY services/agents/pyproject.toml services/agents/
COPY services/mcp/pyproject.toml services/mcp/
COPY data/generator/pyproject.toml data/generator/
RUN uv sync --frozen --no-dev --all-packages --no-install-workspace
COPY services/agents/src services/agents/src
COPY services/mcp/src services/mcp/src
COPY data/generator/src data/generator/src
RUN uv sync --frozen --no-dev --all-packages

FROM python:3.12-slim-bookworm
RUN apt-get update -q \
    && apt-get install -y -q --no-install-recommends tesseract-ocr tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin agents
WORKDIR /app
COPY --from=build /app /app
COPY data/policies data/policies
COPY docs/architecture.md docs/architecture.md
COPY evals/retrieval evals/retrieval
COPY evals/baseline.json evals/baseline.json
ENV PATH=/app/.venv/bin:$PATH TRAMITA_MODELS_DIR=/models HOME=/tmp \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8000
CMD ["uvicorn", "tramita_agents.app:app", "--host", "0.0.0.0", "--port", "8000"]
