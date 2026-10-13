.PHONY: setup lint test ingest bronze silver gold check daily

# Usage: make bronze DATE=2026-10-01
DATE ?= $(shell date +%F)

setup:
	uv sync --extra dev

lint:
	uv run ruff check .

test:
	uv run pytest

ingest:
	uv run python -m ingestion.incremental --table orders --date $(DATE)
	uv run python -m ingestion.incremental --table order_items --date $(DATE)

bronze:
	uv run python -m pipeline.load_bronze --date $(DATE)

silver:
	uv run python -m pipeline.run_sql silver

gold:
	uv run python -m pipeline.run_sql gold

check:
	uv run python -m pipeline.checks

daily:
	uv run python -m pipeline.run_daily --date $(DATE)
