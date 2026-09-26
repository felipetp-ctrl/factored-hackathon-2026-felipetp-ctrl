.PHONY: install test lint api
install:
	cd backend && uv sync
test:
	cd backend && uv run pytest -q
lint:
	cd backend && uvx ruff check --select F,E9 src tests
api:
	cd backend && uv run uvicorn dispute_ops.main:app --reload --port 8000
