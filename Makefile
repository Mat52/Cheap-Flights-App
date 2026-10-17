# Shortcuts for day-to-day work. Run `make` or `make help` for the list.
# Docker Compose reads ports and credentials from .env (see .env.example).

.DEFAULT_GOAL := help
.PHONY: help up up-ghcr down restart ps logs stats shell db tools health lint test check clean

GHCR_IMAGE  := ghcr.io/mat52/cheap-flights-web:latest
LOCAL_IMAGE := cheap-flights-web:local
# Host port of the web UI, taken from .env so `make health` hits the right one.
PORT := $(or $(shell grep -E '^PORT=' .env 2>/dev/null | cut -d= -f2),5000)
# Prefer the project venv for lint/test when it exists.
BIN := $(if $(wildcard venv/bin/python),venv/bin/,)

help: ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

## --- Docker Compose ---

up: ## Build the image from local code and start web + db
	docker compose up --build -d
	@echo "→ http://localhost:$(PORT)"

up-ghcr: ## Start web + db from the CI-built image in GHCR (no local build)
	docker pull $(GHCR_IMAGE)
	docker tag $(GHCR_IMAGE) $(LOCAL_IMAGE)
	docker compose up -d --no-build
	@echo "→ http://localhost:$(PORT)"

down: ## Stop and remove containers (database data is kept)
	docker compose down

restart: ## Restart the web container
	docker compose restart web

ps: ## Container status and health
	docker compose ps

logs: ## Follow web logs (Ctrl+C to stop)
	docker compose logs -f web

stats: ## CPU / memory usage snapshot
	docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'

shell: ## Open a shell inside the web container
	docker compose exec web bash

db: ## Open psql inside the db container
	docker compose exec db sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

tools: ## Also start pgAdmin on http://localhost:8080
	docker compose --profile tools up -d

health: ## Query /healthz and /readyz
	@printf 'healthz: '; curl -s localhost:$(PORT)/healthz
	@printf 'readyz:  '; curl -s localhost:$(PORT)/readyz

clean: ## Stop everything AND delete the database volume (asks first)
	@printf 'This deletes all saved flights. Type "yes" to continue: '; read ans; [ "$$ans" = yes ]
	docker compose --profile tools down -v

## --- Code quality (same checks as CI) ---

lint: ## Run ruff
	$(BIN)ruff check .

test: ## Run pytest
	$(BIN)pytest

check: lint test ## Run lint + tests
