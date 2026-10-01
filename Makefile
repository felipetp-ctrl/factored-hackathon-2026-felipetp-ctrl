# Every command runs from the repo root; `make` alone lists them.
.DEFAULT_GOAL := help
MLFLOW := MLFLOW_DISABLE_AGENT_HINT=1

.PHONY: help install test lint typecheck check api web \
        eval eval-channels uncertainty calibration figures \
        data data-proof catalog insights \
        train fraud-audit learnability mlflow-ui

help: ## List the commands
	@awk 'BEGIN {FS = ":.*## "} /^##@/ {printf "\n%s\n", substr($$0, 5)} /^[a-z-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

##@ Develop
install: ## Install backend dependencies (uv)
	cd backend && uv sync
test: ## Offline backend tests (no API calls)
	cd backend && uv run pytest -q
lint: ## Ruff on the backend (rules in backend/pyproject.toml)
	cd backend && uvx ruff check src tests
typecheck: ## TypeScript check of the web app
	cd frontend && pnpm install --frozen-lockfile && pnpm typecheck
check: lint test typecheck ## Everything CI runs, except the pipeline smoke run
api: ## API on http://localhost:8000 (OpenAPI at /docs)
	cd backend && uv run uvicorn dispute_ops.main:app --reload --port 8000
web: ## Web app on http://localhost:3000
	cd frontend && pnpm install && pnpm dev

##@ Evaluate
eval: ## Conversation evaluation; pass options in ARGS="…" (docs/evaluation.md)
	cd backend && uv run python -m dispute_ops.evaluation $(ARGS)
eval-channels: ## channels-v1 test split: letters and fraud-alert answers, no model calls
	cd backend && uv run python -m dispute_ops.evaluation.channels_eval --set ../eval/scenarios/channels-v1.json --split test --db demo_data/dispute_ops.db --out ../eval/results/channels-v1-test
uncertainty: ## 95% intervals for the headline numbers
	cd backend && uv run python -m dispute_ops.evaluation.uncertainty
calibration: ## Out-of-sample calibration of the intent classifier
	cd backend && uv run --group ml python -m dispute_ops.ml.calibration
figures: ## Regenerate docs/figures from silver and committed results
	cd backend && uv run --group ml python -m dispute_ops.pipeline.figures

##@ Data (needs the organizer data in data/raw/)
data: ## Bronze → silver → gold, quality report, demo export, catalog
	cd backend && uv run python -m dispute_ops.pipeline $(ARGS) && uv run python -m dispute_ops.pipeline.catalog
data-proof: ## Prove incremental silver equals a full rebuild
	cd backend && uv run python -m dispute_ops.pipeline.incremental_proof --work /tmp/dispute-ops-proof
catalog: ## Regenerate docs/data_catalog.md from the contracts
	cd backend && uv run python -m dispute_ops.pipeline.catalog
insights: ## Operating insights (docs/analysis, Insights tab)
	cd backend && uv run --group ml python -m dispute_ops.pipeline.insights

##@ Machine learning
train: ## Train the intent classifier (MLflow run)
	cd backend && $(MLFLOW) uv run --group ml python -m dispute_ops.ml train $(ARGS)
fraud-audit: ## Fraud label learnability audit
	cd backend && $(MLFLOW) uv run --group ml python -m dispute_ops.ml fraud-audit
learnability: ## Learnability scan of nine targets
	cd backend && $(MLFLOW) uv run --group ml python -m dispute_ops.ml learnability
mlflow-ui: ## MLflow UI on http://localhost:5001
	cd backend && uv run --group ml mlflow ui --backend-store-uri sqlite:///../mlruns/mlflow.db --port 5001
