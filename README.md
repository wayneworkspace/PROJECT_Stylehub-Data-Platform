# StyleHub Data Platform

[![CI](https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform/actions/workflows/ci_test.yml/badge.svg)](https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform/actions/workflows/ci_test.yml)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Cloud](https://img.shields.io/badge/cloud-GCP-4285F4)

A daily ELT pipeline that turns the StyleHub online shop's raw tables and its live Postgres database into tested BigQuery tables, a health dashboard and an EDA page. Built with Python, Airflow 3, dbt, BigQuery, GCS, Terraform and Streamlit.

## 1. Business Context & Goals

* **Business problem:** StyleHub's orders, items, products, shipments, users and web events sit in raw tables and a live Postgres database. Analysts cannot trust or query them cheaply: there is no history, no tests, no partitioning, and nobody knows whether yesterday's data arrived.
* **Project goal:** Load both sources every day without duplicates, keep every raw file, build tested facts, dimensions and business tables in BigQuery under a cost cap, and show pipeline health and data quality on one page.

## 2. Pipeline Architecture

```text
Course tables (BigQuery) --full load--> Raw Zone (GCS Parquet) -> Bronze -> Silver -> Gold --> Streamlit
Postgres (course DB) --incremental-->  Raw Zone (GCS, pg_*)    -> Bronze -> Silver -> Gold --> Streamlit EDA
Products API (dummyjson.com) --pages--> Raw Zone (GCS, api_*) -> Bronze -> Silver

Airflow DAG stylehub_daily, 02:00 UTC, two branches:
  ingest    -> bronze    -> silver    -> gold
  pg_ingest -> pg_bronze -> pg_silver -> pg_gold
  [gold, pg_gold] -> freshness (fails when a Bronze table is older than 26 hours)
Airflow DAG stylehub_api, 02:30 UTC (TaskFlow API):
  api_ready (sensor) -> plan_pages -> fetch_page x N (mapped, pool) -> any_rows (branch) -> api_bronze -> api_silver
Every step attempt is recorded in stylehub_ops.pipeline_runs; failures post to Discord.
```

| Step | Description | Source code path |
| --- | --- | --- |
| **Sources** | Settings, GCP and Postgres clients, retry with backoff, one-time CSV upload | `src/1_source/` |
| **Ingestion** | Full load of course tables with a schema check; incremental Postgres load by `updated_at` watermark with a 1-day lookback; paged products API with retries on 429/5xx; append-only Parquet in Raw | `src/2_ingestion/` |
| **Bronze** | Write-audit-publish: load into staging, check row counts against the Raw file, then replace the day's partition | `src/3_storage/` |
| **Silver** | Newest row per id, typed columns, facts and dimensions with grain tests; SCD Type 2 product snapshot | `dbt_project/models/staging/`, `dbt_project/models/marts/core/`, `dbt_project/models/marts/pg_core/` |
| **Gold** | Business rules: revenue, top customers, return rate, delivery time, order value; contracts and unit tests | `dbt_project/models/marts/reporting/`, `dbt_project/models/marts/pg_reporting/` |
| **Serving** | Streamlit pipeline health page and EDA page (quality, duplicates, outliers, KPIs, correlation) | `src/5_serving/` |
| **Orchestration** | `stylehub_daily` (course and Postgres branches) and `stylehub_api` (TaskFlow: sensor, Connection, Variable, XCom, dynamic task mapping, branch, pool) | `dags/` |
| **Monitoring** | Discord alerts on failed tasks, timeouts and stale data; BigQuery job-error alert in Cloud Monitoring | `src/0_utils/alerts.py`, `src/5_serving/freshness.py`, `infra/terraform/monitoring.tf` |

## 3. Technologies Used & Rationale

| Category | Technology | Rationale |
| --- | --- | --- |
| **Cloud / Warehouse** | Google Cloud Storage, BigQuery | GCS keeps every raw file cheaply; BigQuery gives partitions, clustering and a per-query bytes cap |
| **Sources** | SQLAlchemy, psycopg2, pandas | Chunked, consistent `REPEATABLE READ` reads from Postgres straight into DataFrames |
| **Transformation** | dbt (dbt-bigquery), `dbt_utils` | Modular SQL with tests, contracts, unit tests, snapshots, seeds, exposures and lineage; `dbt_utils` gives ready generic tests |
| **Orchestration** | Apache Airflow 3 | Daily schedule, retries, timeouts and backfills with clear task dependencies |
| **Monitoring** | Discord webhook, Cloud Monitoring | A chat message reaches people at once; the log metric also catches failures outside Airflow, such as dbt in CD |
| **Serving** | Streamlit, Altair | A Python-only dashboard; Altair charts ship with Streamlit, no extra dependency |
| **Infrastructure** | Terraform, Workload Identity Federation, Secret Manager | Every cloud resource in code, remote state, short-lived GitHub tokens instead of key files; server secrets kept out of Terraform state |
| **Code & Quality** | Python 3.13, uv, Ruff, pytest, SQLFluff, pre-commit, colorlog | Same checks on a laptop and in CI; colored terminal logs and plain log files |

## 4. Results Achieved

* **Data volume:** one daily run (data day 2026-10-16) loaded 434,986 course rows and 975,226 Postgres rows in the first full Postgres load; the partitioned `events` table holds about 108 million rows (15 GB).
* **Performance:** course branch 259 s end to end (ingest 79 s, bronze 28 s, silver 110 s, gold 41 s); Postgres ingest 105 s and Bronze 40 s for the full first load; the next incremental run read 81,271 Postgres rows in 25 s.
* **Cost control:** every query is capped at 50 GB billed; `events` is partitioned by day and clustered by `event_type, product_id`; the freshness query reads free table metadata; static events stay out of the nightly build, so the Silver step bills 0.41 GB instead of about 6.7 GB.
* **Bytes per query** (dry runs, `include/scripts/dry_run_report.py`): the same events question scans 12,902 MB with every column, 2,380 MB with three columns, 177 MB for one day (partition) and 13 MB for one day of purchases (partition plus cluster).
* **Quality:** dbt passed 29 Silver and 13 Gold checks on the course branch and 26 Silver checks on the Postgres branch; unit tests cover 100% of 671 Python statements.
* **Insights:** the EDA page reads 316,358 Postgres order items of the last 90 days; it found no rule violations (no negative amounts, `amount` always equals `sale_price * quantity`), and 5.7% to 9.4% IQR outliers in price, quantity and amount.

*Current limitations:* runs locally in Docker with one service account key; the Airflow VM is ready in Terraform but off (`ENABLE_AIRFLOW_VM`). Postgres deletes are found by a daily full id compare, not by change data capture. Product cost history starts on 2026-10-01, so older sales use the first known cost. The first Postgres load left some orders without their customer and some items without their order (dbt warnings); the next incremental run fixed the customers, but items without an order remain a warning.

## Quick Start

### Prerequisites

* [uv](https://docs.astral.sh/uv/) and Python 3.13
* Docker Desktop with Docker Compose
* A Google Cloud project, Terraform 1.9 or newer, and the course Postgres URL in `secrets/.env`

### Install and run

```powershell
# 1. Clone the repository
git clone <repository-url>
cd PROJECT_Stylehub-Data-Platform

# 2. Install the environment and dependencies
uv sync --extra dev --extra dbt --extra serving
uv run dbt deps --project-dir dbt_project --profiles-dir dbt_project   # dbt_utils

# 3. Configure environment variables
copy .env.example secrets\.env   # fill in every value; keep secrets/ out of Git

# 4. Create the cloud resources (bash), then load the course data once
#    TF_STATE_BUCKET=<state-bucket> infra/scripts/deploy.sh apply
uv run python -m src.1_source.load_csv
uv run python -m src.3_storage.events_bronze
uv run dotenv -f secrets/.env run -- dbt build --project-dir dbt_project --profiles-dir dbt_project --select tag:events
```

Run with Docker:

```powershell
docker compose --env-file secrets/.env --profile airflow up -d --build   # Airflow UI on AIRFLOW_WEB_PORT
docker compose --env-file secrets/.env --profile serving up -d --build   # dashboard on http://localhost:8501
```

The pipeline runs only through Airflow. `docs/RUNBOOK.md` covers setup and daily operation; `docs/ERRORS.md` lists error messages and fixes.

## Code Quality & CI/CD

Before opening a Pull Request, make sure all of these checks pass:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
uvx pre-commit run --all-files
```

* **CI pipeline (`ci_test.yml`):** pre-commit (ruff, gitleaks), pytest with 100% coverage, `requirements.txt` in sync with `uv.lock`, `dbt parse`, SQLFluff, Terraform `fmt`, `validate` and `plan`, both Docker images, and the DAG test inside the Airflow image.
* **CD pipeline (`cd_deploy.yml`):** after CI passes on `main`, applies Terraform, pushes the tested Airflow image tagged with the commit id, and runs `dbt build` on the real datasets.

## Project Structure

```text
src/            # Python source by stage: 1_source ... 5_serving, plus 0_utils/logger.py
dags/           # Airflow DAG and its helper
dbt_project/    # dbt models, tests, macros, snapshot
include/sql/    # Plain SQL run by Python (events build, dashboard queries)
infra/          # Terraform and the deploy script
config/         # Airflow logging config
tests/          # pytest unit tests and the DAG integrity test
docs/           # RUNBOOK.md, ERRORS.md, SPEC.md (other docs stay local)
```

> **Note:** Never commit `secrets/`, keys, `.env` files, Terraform state or the course data. Work on a feature branch (`feature/...`, `fix/...`) and merge through a Pull Request that passes `ci_test.yml`. Errors and fixes are in `docs/ERRORS.md`.
