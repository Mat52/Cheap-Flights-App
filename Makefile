# Shortcuts for day-to-day work. Run `make` or `make help` for the list.
# Docker Compose reads ports and credentials from .env (see .env.example).

.DEFAULT_GOAL := help
.PHONY: help up up-ghcr down restart ps logs stats shell db tools health clean \
	k8s-up k8s-config k8s-deploy k8s-dev k8s-status k8s-logs k8s-restart \
	k8s-watcher-run k8s-watcher-on k8s-watcher-off k8s-down lint test check

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

## --- Kubernetes (local kind cluster) ---

KIND_CLUSTER := cheap-flights
K8S_NS       := cheap-flights
TRAEFIK_CHART_VERSION := 41.6.1
KUBECTL      := kubectl --context kind-$(KIND_CLUSTER) -n $(K8S_NS)
K8S_URL      := http://flights.localhost:8081

k8s-up: ## Create the kind cluster, install Traefik, deploy the app
	@kind get clusters 2>/dev/null | grep -qx $(KIND_CLUSTER) || kind create cluster --config k8s/kind-config.yaml
	helm repo add traefik https://traefik.github.io/charts --force-update >/dev/null
	helm upgrade --install traefik traefik/traefik --version $(TRAEFIK_CHART_VERSION) \
		--kube-context kind-$(KIND_CLUSTER) --namespace traefik --create-namespace \
		--values k8s/traefik-values.yaml --wait
	$(MAKE) k8s-deploy

k8s-config: ## Generate k8s/secrets.env and k8s/watchlist.json (gitignored)
	@umask 077; grep -E '^(DB_USER|DB_PASSWORD|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=' .env > k8s/secrets.env
	@cp app/watchlist.json k8s/watchlist.json 2>/dev/null || cp app/watchlist.example.json k8s/watchlist.json
	@echo "k8s/secrets.env and k8s/watchlist.json generated"

k8s-deploy: k8s-config ## Apply the manifests (kubectl apply -k k8s/) and wait for rollout
	kubectl --context kind-$(KIND_CLUSTER) apply -k k8s/
	$(KUBECTL) rollout status statefulset/postgres --timeout=180s
	$(KUBECTL) rollout status deployment/web --timeout=600s
	@echo "→ $(K8S_URL)"

# JSON patch ops pointing a pod template's first container at the local :dev image.
dev-image-patch = {"op":"replace","path":"$(1)/containers/0/image","value":"cheap-flights-web:dev"},{"op":"replace","path":"$(1)/containers/0/imagePullPolicy","value":"Never"}

k8s-dev: ## Build the image from local code, load it into kind, and run it (undo: make k8s-deploy)
	docker build -f docker/Dockerfile -t cheap-flights-web:dev .
	kind load docker-image cheap-flights-web:dev --name $(KIND_CLUSTER)
	@# pullPolicy Never: use the image loaded into the node, never a registry.
	$(KUBECTL) patch deployment/web --type=json -p '[$(call dev-image-patch,/spec/template/spec)]'
	$(KUBECTL) patch cronjob/price-watcher --type=json -p '[$(call dev-image-patch,/spec/jobTemplate/spec/template/spec)]'
	$(KUBECTL) rollout status deployment/web --timeout=300s

k8s-status: ## Pods, services, ingress, cronjob and volumes
	$(KUBECTL) get pods,svc,ingress,cronjob,jobs,pvc

k8s-logs: ## Follow web pod logs
	$(KUBECTL) logs -f deployment/web

k8s-restart: ## Restart web (re-pulls :latest from GHCR)
	$(KUBECTL) rollout restart deployment/web
	$(KUBECTL) rollout status deployment/web --timeout=600s

k8s-watcher-run: ## Run one price-watcher check now and follow its logs
	$(KUBECTL) create job --from=cronjob/price-watcher price-watcher-manual-$$(date +%s)
	@sleep 3; $(KUBECTL) logs -f -l app.kubernetes.io/name=price-watcher --tail=-1 --max-log-requests=1 --pod-running-timeout=5m || true

k8s-watcher-on: ## Enable the price-watcher schedule (disable the GitHub Actions one first!)
	$(KUBECTL) patch cronjob/price-watcher -p '{"spec":{"suspend":false}}'

k8s-watcher-off: ## Suspend the price-watcher schedule
	$(KUBECTL) patch cronjob/price-watcher -p '{"spec":{"suspend":true}}'

k8s-down: ## Delete the whole kind cluster (and its data)
	kind delete cluster --name $(KIND_CLUSTER)

## --- Code quality (same checks as CI) ---

lint: ## Run ruff
	$(BIN)ruff check .

test: ## Run pytest
	$(BIN)pytest

check: lint test ## Run lint + tests
