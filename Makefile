PYTHON ?= python3.12
UV ?= uv

.PHONY: install lint test run-api crawl-ajira

install:
	$(UV) sync --dev
	$(UV) run playwright install chromium

lint:
	$(UV) run ruff check .
	$(UV) run mypy src tests

test:
	$(UV) run pytest

run-api:
	$(UV) run uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload

crawl-ajira:
	$(UV) run python -m app.crawler.crawl_ajira --once
