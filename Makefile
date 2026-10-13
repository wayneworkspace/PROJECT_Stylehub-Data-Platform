.PHONY: setup lint test test-integration up down docker-build ingest bronze silver gold check daily

# Usage: make bronze DATE=2026-10-01
DATE ?= $(shell date +%F)

setup:
	uv sync --extra dev

lint:
	uv run ruff check .

test:
	uv run pytest

# Needs the local Postgres: make up
test-integration:
	PG_HOST=localhost PG_PORT=5432 PG_DATABASE=stylehub PG_USER=stylehub \
	PG_PASSWORD=$${LOCAL_PG_PASSWORD:-stylehub_local} uv run pytest -m integration

up:
	docker compose up -d postgres

down:
	docker compose down -v

docker-build:
	docker build -t stylehub-pipeline .

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
