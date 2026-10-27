.DEFAULT_GOAL := help
SHELL         := /bin/bash

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: check
check: ## Validate local prerequisites (python3, gcloud)
	@command -v python3 >/dev/null 2>&1 && echo "python3: OK" || echo "python3: MISSING"
	@command -v gcloud >/dev/null 2>&1 && echo "gcloud: OK" || echo "gcloud: MISSING"
	@test -f agent/.env && echo "agent/.env: OK" || echo "agent/.env: missing (cp agent/.env.example agent/.env)"

.PHONY: setup
setup: setup-agent ## First-time local setup (alias for setup-agent)

.PHONY: setup-agent
setup-agent: ## Install the agent's Python dependencies into agent/.venv
	cd agent && \
	  (test -d .venv || python3 -m venv .venv) && \
	  .venv/bin/pip install -q -r requirements.txt -r requirements-dev.txt

.PHONY: dev-agent
dev-agent: ## Run the Heat Planner UI locally (http://127.0.0.1:8080)
	cd agent && ./run.sh

.PHONY: build-agent
build-agent: ## Build the agent's container image
	docker build -t heat-planner agent

.PHONY: test-agent
test-agent: ## Run the agent's pytest suite
	cd agent && .venv/bin/python -m pytest

.PHONY: load-data
load-data: ## Load BigQuery data for a city (usage: make load-data CITY=dallas)
	bash scripts/load.sh $(CITY)

.PHONY: install-hooks
install-hooks: ## Install the pre-commit secret-scan hook
	cp hooks/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit

.PHONY: audit
audit: ## Run the modernization/governance audit script
	bash scripts/modernization-audit.sh

.PHONY: deploy-agent
deploy-agent: ## Deploy the agent to Cloud Run (set PROJECT=<gcp-project>)
	gcloud run deploy heat-planner --source agent --region us-central1 \
	  --set-env-vars GOOGLE_CLOUD_PROJECT=$(PROJECT),BQ_DATASET=a4i_climate --min-instances 1
