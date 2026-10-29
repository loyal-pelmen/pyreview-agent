.PHONY: dev lint format test run

dev:
	uv sync --locked

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run ty check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

test:
	uv run pytest

run:
	uv run uvicorn pyreview.main:app --host 127.0.0.1 --port 8000 --reload
