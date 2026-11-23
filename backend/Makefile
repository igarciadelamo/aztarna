.PHONY: setup run test lint format docker tips-strings

setup:
	@command -v uv >/dev/null || { echo "uv not found: brew install uv (or see https://docs.astral.sh/uv/)"; exit 1; }
	uv sync
	uv run python -c "from aztarna.astro import eph; eph()"  # DE421 ephemeris, ~17 MB, once
	uv run pre-commit install

run:
	@echo "Dev console: http://127.0.0.1:8000/dev"
	AZTARNA_DEV_UI=1 uv run uvicorn aztarna.main:app --reload --no-access-log

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

# English <string> entries for the Android app, generated from aztarna/tips.py (see android/README.md).
tips-strings:
	@uv run python -c "from xml.sax.saxutils import escape; from aztarna.tips import TEXT; \
	[print(f'    <string name=\"tip_{c.lower()}\">' + escape(t).replace(chr(39), chr(92) + chr(39)) + '</string>') for c, t in TEXT.items()]"
