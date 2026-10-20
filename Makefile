.PHONY: install run test lint format seed refresh

install:          ## create the virtual environment and install dependencies
	uv sync

run:              ## start the app on http://localhost:8000
	uv run uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000

test:
	uv run pytest -q

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format . && uv run ruff check . --fix

seed:             ## (re)load the synthetic demo data
	uv run python -m app.cli seed

refresh:          ## lifecycle refresh from var/lifecycle/*.csv
	uv run python -m app.cli refresh
