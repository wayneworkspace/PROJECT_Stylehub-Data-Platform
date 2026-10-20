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

Daily at 02:00 UTC, GitHub Actions (pipeline.yml) or Airflow (stylehub_daily), same steps:
  ingest    -> bronze    -> silver    -> gold
  pg_ingest -> pg_bronze -> pg_reconcile -> pg_silver -> pg_gold   (paused: PG_ENABLED = False)
  [gold, pg_gold] -> freshness (fails when a Bronze table is older than 26 hours)
12:00 UTC watchdog.yml: freshness again, so a run that never started still alerts.
Every step attempt is recorded in stylehub_ops.pipeline_runs; failures post to Discord.

Deploy (CD, after CI on main): terraform apply (prod, dev) -> push tested images
  -> dbt build on staging (_dev datasets) -> approval -> dbt build on production
  -> dashboard image on Cloud Run
```

| Step | Description | Source code path |
| --- | --- | --- |
| **Sources** | Settings, GCP and Postgres clients, retry with backoff, one-time CSV upload | `src/1_source/` |
| **Ingestion** | Full load of course tables with a schema check; incremental Postgres load by `updated_at` watermark with a 1-day lookback, read in 50,000-row chunks with one fixed Parquet schema per table; append-only Parquet in Raw | `src/2_ingestion/` |
| **Bronze** | Write-audit-publish: load into staging, check row counts against the Raw file, then replace the day's partition; a daily id compare finds rows deleted in Postgres | `src/3_storage/` |
| **Silver** | Newest row per id, typed columns, facts and dimensions with grain tests; rows deleted in Postgres kept with `is_deleted`; SCD Type 2 products (new version only when the tracked columns' hash changes, `product_key` surrogate key); `pg_fact_orders_versions` for as-of questions | `dbt_project/models/staging/`, `dbt_project/models/marts/core/`, `dbt_project/models/marts/pg_core/` |
| **Gold** | Business rules: revenue, top customers, return rate, delivery time, order value, without deleted rows; published monthly revenue kept as version 1, a `restated` version added only on request (`restate_months` var); contracts and unit tests | `dbt_project/models/marts/reporting/`, `dbt_project/models/marts/pg_reporting/` |
| **Serving** | Streamlit pipeline health page and EDA page (quality, missing values, duplicates, KDE, time features, IQR and z-score outliers, KPIs, correlation, conclusions) | `src/5_serving/` |
| **Orchestration** | Daily run on GitHub Actions (free; on demand with a `data_date` for backfills) and the same steps as the Airflow DAG `stylehub_daily` for local runs; a test keeps both lists equal | `.github/workflows/pipeline.yml`, `dags/` |
| **Monitoring** | Discord alerts on failed tasks, runs, CI/CD and stale data; watchdog run; Cloud Monitoring alerts on BigQuery job errors and on the dashboard health check; local Prometheus and Grafana for the Airflow host | `src/0_utils/alerts.py`, `src/5_serving/freshness.py`, `infra/terraform/monitoring.tf`, `config/monitoring/` |

## 3. Technologies Used & Rationale

| Category | Technology | Rationale |
| --- | --- | --- |
| **Cloud / Warehouse** | Google Cloud Storage, BigQuery | GCS keeps every raw file cheaply; BigQuery gives partitions, clustering and a per-query bytes cap |
| **Sources** | SQLAlchemy, psycopg2, pandas | Chunked, consistent `REPEATABLE READ` reads from Postgres straight into DataFrames |
| **Transformation** | dbt (dbt-bigquery), `dbt_utils` | Modular SQL with tests, contracts, unit tests, snapshots, seeds, exposures and lineage; `dbt_utils` gives ready generic tests |
| **Orchestration** | GitHub Actions schedule, Apache Airflow 3 | GitHub runs the daily job for free with no machine to keep on; Airflow gives the same DAG with retries and a UI for local runs |
| **Monitoring** | Discord webhook, Cloud Monitoring, Prometheus, Grafana | A chat message reaches people at once; Cloud Monitoring also catches failures outside the pipeline; Prometheus exporters show the Airflow host and its database |
| **Serving** | Streamlit, Altair, Cloud Run | A Python-only dashboard; Cloud Run gives HTTPS, IAM sign-in and scale to zero inside the free tier |
| **Infrastructure** | Terraform (module `bigquery_dataset`, prod and dev roots), Workload Identity Federation, Secret Manager, Ansible | Every cloud resource in code, one module reused by two environments with separate state, short-lived GitHub tokens instead of key files; Ansible sets up the optional Airflow VM over IAP |
| **Delivery** | Docker, Artifact Registry, GitHub Environments | CI builds and scans each image once; CD pushes exactly that image; production waits for approval after staging passes |
| **Code & Quality** | Python 3.13, uv, Ruff, pytest, SQLFluff, pre-commit, gitleaks, pip-audit, Trivy, tflint, checkov, Dependabot, Jenkins | Same checks on a laptop, in CI and on a local Jenkins; known vulnerabilities and risky Terraform stop a pull request |

## 4. Results Achieved

* **Data volume:** one daily run (data day 2026-10-16) loaded 434,986 course rows and 975,226 Postgres rows in the first full Postgres load; the partitioned `events` table holds about 108 million rows (15 GB).
* **Performance:** course branch 259 s end to end (ingest 79 s, bronze 28 s, silver 110 s, gold 41 s); Postgres ingest 105 s and Bronze 40 s for the full first load; the next incremental run read 81,271 Postgres rows in 25 s.
* **Cost control:** made to stay at about 0 USD: the daily run uses free GitHub Actions minutes, the dashboard scales to zero on Cloud Run, Artifact Registry keeps 2 images (0.5 GB free), and a 1 USD budget e-mails at 50, 90 and 100%; every query is capped at 50 GB billed; `events` is partitioned by day and clustered by `event_type, product_id`; the freshness query reads free table metadata; static events stay out of the nightly build, so the Silver step bills 0.41 GB instead of about 6.7 GB.
* **Bytes per query** (dry runs, `include/scripts/dry_run_report.py`): the same events question scans 12,902 MB with every column, 2,380 MB with three columns, 177 MB for one day (partition) and 13 MB for one day of purchases (partition plus cluster).
* **Quality:** dbt passed 29 Silver and 13 Gold checks on the course branch and 26 Silver checks on the Postgres branch; unit tests cover 100% of 882 Python statements.
* **Insights:** the EDA page reads 316,358 Postgres order items of the last 90 days; it found no rule violations (no negative amounts, `amount` always equals `sale_price * quantity`), and 5.7% to 9.4% IQR outliers in price, quantity and amount.

*Current limitations:* the Postgres branch is paused since 2026-10-20 because the course database host no longer resolves; its Silver and Gold tables keep the last good load until `POSTGRES_URL` works and `PG_ENABLED` is set back to `True` in `dags/main_etl_dag.py`. The Airflow VM is ready in Terraform and Ansible but off (`ENABLE_AIRFLOW_VM`), because it is not in the free tier. GitHub stops scheduled workflows after 60 days without repository activity. Postgres deletes are found by a daily full id compare, not by change data capture. Product cost history starts on 2026-10-01, so older sales use the first known cost. The first Postgres load left some orders without their customer and some items without their order (dbt warnings); the next incremental run fixed the customers, but items without an order remain a warning.

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
docker compose --env-file secrets/.env --profile airflow --profile monitoring up -d --build   # Prometheus :9090, Grafana :3000
docker compose --profile jenkins up -d   # Jenkins :8090; new Pipeline job, "Pipeline script from SCM", this repository
```

Without a key file: `gcloud auth application-default login --impersonate-service-account=<sa-pipeline e-mail>` (your account must be in the GitHub variable `DEVELOPER_MEMBERS`). Open the Cloud Run dashboard with `gcloud run services proxy stylehub-dashboard --region asia-southeast1 --port 8501`. Back up the local Airflow database with `infra/scripts/airflow_db_backup.sh backup`.

In production the pipeline runs from `.github/workflows/pipeline.yml` (Actions > Pipeline > Run workflow for a backfill). `docs/RUNBOOK.md` covers setup and daily operation; `docs/ERRORS.md` lists error messages and fixes.

## Code Quality & CI/CD

Before opening a Pull Request, make sure all of these checks pass:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
uvx pre-commit run --all-files
```

* **CI pipeline (`ci_test.yml`):** pre-commit (ruff, gitleaks), pytest with 100% coverage, `requirements.txt` in sync with `uv.lock`, `dbt parse`, SQLFluff, pip-audit, Ansible syntax, Terraform `fmt`, `validate`, tflint, checkov and `plan` (prod and dev), both Docker images with layer caching, a Trivy scan of each, and the DAG test inside the Airflow image. Required for every pull request to `main`.
* **CD pipeline (`cd_deploy.yml`):** after CI passes on `main`, applies Terraform (prod and dev), pushes both tested images (tags: commit id and `main`), runs `dbt build` on staging, waits for approval of the `production` environment, runs `dbt build` on production, then puts the tested dashboard on Cloud Run.
* **Other workflows:** `pipeline.yml` (daily run, backfills), `watchdog.yml` (alert when the run did not happen), `restate.yml` (publish a corrected month after approval). CI, CD and run failures post to Discord. Dependabot opens weekly update pull requests.

## Project Structure

```text
src/            # Python source by stage: 1_source ... 5_serving, plus 0_utils/logger.py
dags/           # Airflow DAG and its helper
dbt_project/    # dbt models, tests, macros, snapshot
include/sql/    # Plain SQL run by Python (events build, dashboard queries)
infra/          # Terraform (prod root, envs/dev, modules/), Ansible for the VM, deploy and backup scripts
config/         # Airflow logging config, Prometheus and Grafana config (config/monitoring/)
.github/        # CI, CD, daily pipeline, watchdog and restate workflows; Dependabot
tests/          # pytest unit tests and the DAG integrity test
docs/           # RUNBOOK.md, ERRORS.md, SPEC.md (other docs stay local)
```

> **Note:** Never commit `secrets/`, keys, `.env` files, Terraform state or the course data. Work on a feature branch (`feature/...`, `fix/...`) and merge through a Pull Request that passes `ci_test.yml`. Errors and fixes are in `docs/ERRORS.md`.
