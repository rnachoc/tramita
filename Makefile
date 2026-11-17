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
.PHONY: up down reset ps logs smoke obs-up
up: ## Start the local infrastructure and wait until every service is healthy
	$(COMPOSE) up -d --wait

smoke: ## Exercise every running service with a real request (vectors, events, search, S3, Temporal)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) bash deploy/compose/smoke-test.sh

down: ## Stop the local infrastructure (keeps data volumes)
	$(COMPOSE) down

reset: ## Stop the local infrastructure and delete its data volumes
	$(COMPOSE) down -v

obs-up: ## Start the observability stack: OTLP collector, Jaeger (:16686), Prometheus (:9090), Grafana (:3000)
	$(COMPOSE) --profile observability up -d otel-collector jaeger prometheus grafana

ps: ## Show infrastructure status
	$(COMPOSE) ps

logs: ## Follow infrastructure logs
	$(COMPOSE) logs -f --tail=100

# --- Python (uv workspace) ----------------------------------------------------
PY_TYPED := services/agents/src services/agents/tests services/mcp/src services/mcp/tests data/generator/src data/generator/tests

.PHONY: py-sync py-lint py-test
py-sync: ## Install the Python workspace
	uv sync --all-packages

py-lint: py-sync ## Lint, check formatting and type-check Python code
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy $(PY_TYPED)

py-test: py-sync ## Run Python tests
	uv run pytest services/agents services/mcp data/generator

# --- Data ---------------------------------------------------------------------------
.PHONY: data data-json
data: py-sync ## Render policy conditions and generate the synthetic dataset (seeded)
	uv run tramita-datagen

data-json: py-sync ## Generate the dataset records only, without rendering documents (fast)
	uv run tramita-datagen --no-documents

.PHONY: seed
seed: ## Load the generated policies into a running core service (TRAMITA_CORE_URL, TRAMITA_API_KEYS)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-seed

.PHONY: eval-extraction
eval-extraction: py-sync ## Evaluate document reading on the generated data (needs `make data`; report in evals/reports)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-eval-extraction $(ARGS)

.PHONY: eval-retrieval
eval-retrieval: py-sync ## Evaluate the policy search (stack up, `make data` and `make index`; report in evals/reports)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-eval-retrieval $(ARGS)

.PHONY: cost-report
cost-report: ## Model calls, tokens, time and (when priced) money per claim and agent (after `make process`)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-cost-report $(ARGS)

.PHONY: scorecard
scorecard: ## Compare the evaluation reports with evals/baseline.json (ARGS="--sections agents" or "--update")
	uv run tramita-eval-baseline $(ARGS)

.PHONY: ingest
ingest: ## Read the generated claims' documents and record them in a running core (stack up, policies seeded)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-ingest $(ARGS)

.PHONY: index
index: py-sync ## Index the policy conditions for search in OpenSearch and pgvector (stack up; downloads models once)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-index-policies $(ARGS)

.PHONY: event-schemas
event-schemas: py-sync ## Regenerate docs/events/claim-event.schema.json from the event contracts
	uv run tramita-event-schemas

.PHONY: worker bridge start-claims
worker: ## Run the claim workflow worker (Temporal; stack up, index built, core running)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-worker $(ARGS)

bridge: ## Signal claim workflows from the claim events on Kafka (core with TRAMITA_EVENTS_ENABLED=true)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-bridge $(ARGS)

start-claims: ## Start one workflow per ingested claim (ARGS="--wait" to wait for them)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-start-claims $(ARGS)

.PHONY: process
process: ## Analyse the open claims with the agents and submit proposals to a running core (after ingest and index)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-process $(ARGS)

.PHONY: eval-agents
eval-agents: ## Evaluate the agents end to end against the expected resolutions (after `make process`)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) uv run tramita-eval-agents $(ARGS)

# --- Review console (Angular) ---------------------------------------------------------
.PHONY: console-install console-test console-build console-up console-e2e
console-install: ## Install the console's dependencies (npm ci)
	cd web/console && npm ci --no-audit --no-fund

console-test: ## Check formatting and run the console's unit tests
	cd web/console && npx prettier --check src && npm test

console-build: ## Build the console for production
	cd web/console && npm run build

console-up: ## Build and start the console on :4200, proxying to the core on the host
	$(COMPOSE) --profile console up -d --build --wait console

console-e2e: ## Review a claim through the console in a real browser (core running, console up)
	cd web/console && npx playwright test

# --- Java (core service) --------------------------------------------------------
.PHONY: core-lint core-test core-run
core-run: ## Run the core service against the local stack (needs `make up`)
	$(if $(ENV_FILE),set -a && . ./$(ENV_FILE) && set +a &&) cd services/core && mvn -B -q spring-boot:run

core-lint: ## Check Java formatting
	cd services/core && mvn -B -q spotless:check

core-test: data-json ## Run Java unit and integration tests (integration tests need Docker)
	cd services/core && mvn -B verify

# --- Aggregates -----------------------------------------------------------------
.PHONY: lint test secrets
lint: py-lint core-lint ## Run every linter

test: py-test core-test ## Run every test suite

secrets: ## Scan the full git history for secrets
	gitleaks git --redact --verbose
