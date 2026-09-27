.PHONY: install test lint api eval web data train fraud-audit mlflow-ui
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
web:
	cd frontend && pnpm install && pnpm dev
data:
	cd backend && uv run python -m dispute_ops.pipeline $(ARGS)
train:
	cd backend && MLFLOW_DISABLE_AGENT_HINT=1 uv run --group ml python -m dispute_ops.ml train $(ARGS)
fraud-audit:
	cd backend && MLFLOW_DISABLE_AGENT_HINT=1 uv run --group ml python -m dispute_ops.ml fraud-audit
mlflow-ui:
	cd backend && uv run --group ml mlflow ui --backend-store-uri sqlite:///../mlruns/mlflow.db --port 5001
