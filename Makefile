.PHONY: install test lint api eval eval-channels figures calibration uncertainty web data data-proof catalog insights train fraud-audit learnability mlflow-ui
install:
	cd backend && uv sync
test:
	cd backend && uv run pytest -q
lint:
	cd backend && uvx ruff check --select F,E9 src tests
api:
	cd backend && uv run uvicorn dispute_ops.main:app --reload --port 8000
eval:
	cd backend && uv run python -m dispute_ops.evaluation $(ARGS)
eval-channels:
	cd backend && uv run python -m dispute_ops.evaluation.channels_eval --set ../eval/scenarios/channels-v1.json --split test --db demo_data/dispute_ops.db --out ../eval/results/channels-v1-test
uncertainty:
	cd backend && uv run python -m dispute_ops.evaluation.uncertainty
calibration:
	cd backend && uv run --group ml python -m dispute_ops.ml.calibration
figures:
	cd backend && uv run --group ml python -m dispute_ops.pipeline.figures
web:
	cd frontend && pnpm install && pnpm dev
data:
	cd backend && uv run python -m dispute_ops.pipeline $(ARGS) && uv run python -m dispute_ops.pipeline.catalog
data-proof:
	cd backend && uv run python -m dispute_ops.pipeline.incremental_proof --work /tmp/dispute-ops-proof
catalog:
	cd backend && uv run python -m dispute_ops.pipeline.catalog
insights:
	cd backend && uv run --group ml python -m dispute_ops.pipeline.insights
train:
	cd backend && MLFLOW_DISABLE_AGENT_HINT=1 uv run --group ml python -m dispute_ops.ml train $(ARGS)
fraud-audit:
	cd backend && MLFLOW_DISABLE_AGENT_HINT=1 uv run --group ml python -m dispute_ops.ml fraud-audit
learnability:
	cd backend && MLFLOW_DISABLE_AGENT_HINT=1 uv run --group ml python -m dispute_ops.ml learnability
mlflow-ui:
	cd backend && uv run --group ml mlflow ui --backend-store-uri sqlite:///../mlruns/mlflow.db --port 5001
