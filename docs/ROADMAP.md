# Roadmap by session

## Session 1: Data Platform
- [x] Code: `src/python/pipeline/setup_gcp.py` and `src/python/pipeline/load_csv.py` (not yet run on a real project)
- [ ] GCP project, GCS bucket, three BigQuery datasets, service account
- [ ] Upload CSVs to GCS, load the 5 tables into BigQuery, compare bytes processed with the original file size
- [ ] `events_partitioned` (`src/sql/bronze/01_events_partitioned.sql`)
- [ ] Measure 3 queries and record them in `docs/DECISIONS.md`, section 1

## Session 2: Data Ingestion
- [x] Code: full load (`--full-load`), schema check, `src/python/pipeline/backfill.py` and a test that a re-run keeps the distinct ids (not yet run on real data)
- [ ] Check `updated_at` of order_items, then choose the watermark (`docs/DECISIONS.md`, section 2)
- [ ] `make ingest` for orders and order_items; backfill 7 days; re-running does not change the distinct id count
- [ ] Ingest `products` from the API into `raw/stylehub/products_api/` (overwrite per day)

## Session 3: Transform and layering
- [x] Write-up: [ETL_VS_ELT.md](ETL_VS_ELT.md), with the "Finance stops counting Returned orders" exercise
- [ ] `make bronze` loads orders, order_items, products
- [ ] Silver `fact_orders`, `fact_order_items`, `dim_products`
- [ ] Gold `daily_revenue`, `make check` passes

## Session 4: Ingestion tool
- [ ] Airbyte VM on GCP, firewall restricted to your own IP
- [ ] Postgres → BigQuery connections for orders, order_items, products, shipments
- [ ] Connector Builder for the StyleHub API
- [ ] Record the sync mode of each table in `docs/DECISIONS.md`, section 3

## Session 5: Data modeling
- [ ] Fill in the design table (question, event, grain, measure, dimensions) for the 5 questions
- [ ] All 5 Silver tables built, `make check` passes the grain check
- [ ] Gold: revenue by category, return rate, delivery time

## DevOps (done)
- [x] Dockerfile and `docker-compose.yaml` with a local Postgres and sample data
- [x] GitHub Actions CI: pre-commit, lint, unit and integration tests, Docker build
- [x] Pre-commit hooks (ruff, gitleaks, file checks) and a locked `uv.lock`
- [x] Logging, `pipeline_runs` history table and Discord failure alerts
- [x] VM files: run script, systemd timers, one service account per job (not yet run on GCP)

## DevOps (next)
See [DEVOPS.md](DEVOPS.md): run on a real VM, retries, a "did not run" alert, Artifact Registry, Terraform.

## After the curriculum
See [EXTENDING.md](EXTENDING.md): dbt, Airflow, Spark. Also add daily incremental data (1,000 to 4,000 rows) so the pipeline runs for real.
