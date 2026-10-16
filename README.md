# StyleHub Data Pipeline

[![CI](https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform/actions/workflows/ci.yaml/badge.svg)](https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform/actions/workflows/ci.yaml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![GCP](https://img.shields.io/badge/cloud-GCP-4285F4)

A small ELT pipeline on Google Cloud for an online-shop dataset. Python loads the data, dbt builds the tables in BigQuery, Airflow runs it every day, and a Streamlit page shows if the pipeline is healthy.

## How the data flows

```
course tables (BigQuery) -> Raw Zone (GCS, Parquet) -> Bronze -> Silver -> Gold
                                                                  (dbt)    (dbt)
Airflow runs the four steps every day.  Streamlit (serving) reads the run log and Bronze.
```

| Step | What it does | Code |
|---|---|---|
| ingest | Copy each table to GCS as a Parquet file. Files are never overwritten | `src/stylehub/ingestion/` |
| bronze | Load the newest file of each day into BigQuery. Running a day twice does not double the rows | `src/stylehub/bronze/` |
| silver | Latest row per id, correct types, facts and dimensions | `dbt/models/staging`, `intermediate`, `marts/core` |
| gold | Business rules, for example "Cancelled orders are not revenue" | `dbt/models/marts/reporting` |
| serving | Streamlit page: pipeline runs and data freshness | `src/stylehub/serving/` |

Every step is logged and saved in the BigQuery table `stylehub_ops.pipeline_runs`.

## What is in each course session

| Session | Where to look |
|---|---|
| 1. Data platform | GCS bucket and datasets (`setup/`), `events_partitioned` with partition and cluster (`sql/bronze/`) |
| 2. Ingestion | Raw Zone path and 3 metadata columns, schema check (`fail` or `absorb`), retry, `--date`, `--backfill-days`, `--incremental` with a lookback (`ingestion/`) |
| 3. Transform and layering | Bronze, Silver, Gold with dbt; rules live in Gold |
| 4. Airbyte | Not built yet |
| 5. Data modeling | Silver facts and dimensions with a grain test on each |
| 6. SCD | `dbt/snapshots/products_history.sql` (Type 2) |

## Tech stack

| Area | Tools |
|---|---|
| Cloud | Google Cloud Storage, BigQuery |
| Code | Python 3.12, pandas, PyArrow, pydantic-settings |
| Transform | dbt (dbt-bigquery) |
| Schedule | Apache Airflow 3 |
| Monitoring | `pipeline_runs` table, Python `logging`, Streamlit |
| DevOps | Docker Compose, GitHub Actions (CI and CD), uv, ruff, mypy, sqlfluff, pre-commit |

## Quick start

You need [uv](https://docs.astral.sh/uv/), a Google Cloud project and Docker (for Airflow and the dashboard).

```powershell
git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform.git
cd PROJECT_Stylehub-Data-Platform
uv sync --extra dev --extra dbt
copy .env.example secrets\.env      # then fill in your values
gcloud auth application-default login
uv run python -m stylehub.setup.setup_gcp          # bucket, datasets, pipeline_runs
uv run python -m stylehub.bronze.events_bronze     # build the big events table once
uv run python -m stylehub.orchestration.run_daily --date 2026-10-01
```

Backfill the last 7 days of one table: `uv run python -m stylehub.ingestion.csv_tables --table orders --date 2026-10-07 --backfill-days 7`

Run with Docker:

```powershell
docker compose --env-file secrets/.env --profile airflow up -d --build   # http://localhost:8080
docker compose --env-file secrets/.env --profile serving up -d --build   # http://localhost:8501
```

Before you say a change is done:

```powershell
uv run ruff check . ; uv run ruff format --check . ; uv run mypy
```

## CI and CD

- **CI** (`.github/workflows/ci.yaml`): pre-commit (ruff, gitleaks), mypy, `dbt parse`, sqlfluff, and a Docker build. No Google Cloud call.
- **CD** (`.github/workflows/cd.yaml`): after CI passes on `main`, push the tested images. The tag is the commit id, never `latest`.

## Project layout

```
src/stylehub/   ingestion/  bronze/  setup/  transform/  orchestration/  serving/  common/
src/stylehub/sql/   Bronze, ops and serving queries
dbt/            Silver and Gold models, tests, snapshot
deploy/         Dockerfiles and the Airflow DAG
```

## Limitations

- The source is the course tables in BigQuery, so every run is a full load. `--date` labels the Raw folder.
- `--incremental` writes to `<table>_incremental` and Bronze does not load it, because Bronze keeps full snapshots.
- Not run yet: a scheduled Airflow run, the Streamlit page, the `products_history` snapshot on real BigQuery.
- One service account does everything on a laptop. No VM was created.

> The StyleHub dataset belongs to the course. This repo holds only code. Never commit `secrets/`, keys or the raw CSV files.
