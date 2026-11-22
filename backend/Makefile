.PHONY: setup run test lint format docker

setup:
	@command -v uv >/dev/null || { echo "uv not found: brew install uv (or see https://docs.astral.sh/uv/)"; exit 1; }
	uv sync
	uv run pre-commit install

run:
	uv run uvicorn aztarna.main:app --reload --no-access-log

test:
	uv run pytest

lint:
	uv run ruff check
	uv run ruff format --check

format:
	uv run ruff check --fix
	uv run ruff format

docker:
	docker build -t aztarna-backend .
	docker run --rm -p 8000:8000 -v aztarna-data:/data aztarna-backend
