# Tramita developer entry points. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE_FILE := deploy/compose/docker-compose.yml
ENV_FILE := $(wildcard .env)
COMPOSE := docker compose -f $(COMPOSE_FILE) $(if $(ENV_FILE),--env-file $(ENV_FILE),)

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Infrastructure -----------------------------------------------------------
.PHONY: up down reset ps logs
up: ## Start the local infrastructure and wait until every service is healthy
	$(COMPOSE) up -d --wait

down: ## Stop the local infrastructure (keeps data volumes)
	$(COMPOSE) down

reset: ## Stop the local infrastructure and delete its data volumes
	$(COMPOSE) down -v

ps: ## Show infrastructure status
	$(COMPOSE) ps

logs: ## Follow infrastructure logs
	$(COMPOSE) logs -f --tail=100

# --- Python (uv workspace) ----------------------------------------------------
PY_TYPED := services/agents/src services/agents/tests data/generator/src data/generator/tests

.PHONY: py-sync py-lint py-test
py-sync: ## Install the Python workspace
	uv sync --all-packages

py-lint: py-sync ## Lint, check formatting and type-check Python code
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy $(PY_TYPED)

py-test: py-sync ## Run Python tests
	uv run pytest services/agents data/generator

# --- Data ---------------------------------------------------------------------------
.PHONY: data
data: py-sync ## Render policy conditions and generate the synthetic dataset (seeded)
	uv run tramita-datagen

# --- Java (core service) --------------------------------------------------------
.PHONY: core-lint core-test
core-lint: ## Check Java formatting
	cd services/core && mvn -B -q spotless:check

core-test: ## Run Java unit and integration tests
	cd services/core && mvn -B verify

# --- Aggregates -----------------------------------------------------------------
.PHONY: lint test secrets
lint: py-lint core-lint ## Run every linter

test: py-test core-test ## Run every test suite

secrets: ## Scan the full git history for secrets
	gitleaks git --redact --verbose
