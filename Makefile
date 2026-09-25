.PHONY: install test lint
install:
	cd backend && uv sync
test:
	cd backend && uv run pytest -q
lint:
	cd backend && uvx ruff check --select F,E9 src tests
