.PHONY: setup lint test test-integration up down docker-build setup-gcp load-csv ingest full-load backfill bronze silver gold check daily

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

# Session 1: create the bucket and datasets, then load the course CSV files
setup-gcp:
	uv run python -m storage.setup_gcp

load-csv:
	uv run python -m storage.load_csv

# Database (Postgres) and API
ingest:
	uv run python -m ingestion.database --table orders --date $(DATE)
	uv run python -m ingestion.database --table order_items --date $(DATE)
	uv run python -m ingestion.api --table users --date $(DATE)

# Whole tables, not one day. Stored under DATE.
full-load:
	uv run python -m ingestion.database --table orders --date $(DATE) --full-load
	uv run python -m ingestion.database --table order_items --date $(DATE) --full-load

# Usage: make backfill FROM=2026-09-25 TO=2026-10-01
backfill:
	uv run python -m orchestration.backfill --from-date $(FROM) --to-date $(TO)

bronze:
	uv run python -m storage.load_bronze --date $(DATE)

silver:
	uv run python -m transform.run_sql silver

gold:
	uv run python -m transform.run_sql gold

check:
	uv run python -m transform.checks

daily:
	uv run python -m orchestration.run_daily --date $(DATE)
