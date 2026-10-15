# Roadmap by session

## Session 1: Data Platform
- [x] Code: `src/python/storage/setup/setup_gcp.py` and `src/python/storage/setup/load_csv.py` (run on a real project)
- [x] GCP project, GCS bucket, BigQuery datasets, service account
- [x] Upload CSVs to GCS, load the 5 tables into BigQuery
- [ ] Compare bytes processed with the original file size
- [x] `events_partitioned` (`src/sql/bronze/01_events_partitioned.sql`, built by `storage.events_bronze`)
- [ ] Measure 3 queries and record them in `docs/design/DECISIONS.md`, section 1

## Session 2: Data Ingestion
- [x] Code: full load, schema check (run on the real CSV tables)
- [x] Checked: the CSV files have no `updated_at`, so the CSV path uses a full load, not a watermark
- [x] `ingestion.csv_tables` for orders, order_items, products and users
- [ ] Backfill 7 days with Airflow; check that re-running does not change the distinct id count

## Session 3: Transform and layering
- [x] Write-up: [ETL_VS_ELT.md](ETL_VS_ELT.md), with the "Finance stops counting Returned orders" exercise
- [x] Bronze loads orders, order_items, products, users
- [x] Silver `fact_orders`, `fact_order_items`, `dim_products`
- [x] Gold `daily_revenue`; the dbt tests pass

## Session 4: Ingestion tool
- [ ] Airbyte VM on GCP, firewall restricted to your own IP
- [ ] Postgres → BigQuery connections for orders, order_items, products, shipments
- [ ] Connector Builder for the StyleHub API
- [ ] Record the sync mode of each table in `docs/design/DECISIONS.md`, section 3

## Session 5: Data modeling
- [ ] Fill in the design table (question, event, grain, measure, dimensions) for the 5 questions
- [x] Silver tables built (plus `fact_events`); the grain tests (unique, not null) pass
- [x] Gold: revenue by category, return rate, delivery time, events per day, funnel
- [ ] Fill in the design table (question, event, grain, measure, dimensions) in `docs/design/DECISIONS.md`

## DevOps (done)
- [x] Dockerfiles in `deploy/` and one `docker-compose.yaml` (profiles: sample Postgres, pipeline, Airflow)
- [x] GitHub Actions CI: pre-commit, lint, unit and integration tests, Docker build
- [x] Pre-commit hooks (ruff, gitleaks, file checks) and a locked `uv.lock`
- [x] Logging, `pipeline_runs` history table and Discord failure alerts
- [x] VM files: run script (the systemd timers were removed; Airflow schedules the pipeline)
- [ ] One service account per job: roles are designed in [DEPLOY_VM.md](../ops/DEPLOY_VM.md); keys are not created yet (one key does everything now)

## DevOps (next)
See [DEVOPS.md](../ops/DEVOPS.md): run on a real VM, retries, a "did not run" alert, Artifact Registry, Terraform.

## After the curriculum
See [EXTENDING.md](EXTENDING.md): dbt and Airflow are in the repo (run on BigQuery from a laptop). Next: Spark, CDC and Kafka. Also add daily incremental data (1,000 to 4,000 rows) so the pipeline runs for real.

Also open: add `dim_date`, and add an architecture diagram image.
