# StyleHub Data Platform Specification

## Scope

| Item | Specification |
|---|---|
| Purpose | Daily ELT turns StyleHub shop data into tested BigQuery tables |
| Sources | Course BigQuery tables, read-only course Postgres database (paused since 2026-10-20) |
| Destination | GCS Raw Zone plus BigQuery Bronze, Silver, Gold datasets |
| Schedule | 02:00 UTC daily: `.github/workflows/pipeline.yml` (same steps as the Airflow DAG `stylehub_daily`); watchdog at 12:00 UTC |
| Consumers | Analysts read Gold; Streamlit shows health and EDA |
| Environment | Daily run on GitHub Actions; local Docker for Airflow and the dashboard; dashboard on Cloud Run; one GCP project, asia-southeast1; about 0 USD |

## Pipeline stages

| Stage | Code | Responsibility |
|---|---|---|
| 1. Sources | `src/1_source/` | Settings, GCP and Postgres clients, retry, CSV upload |
| 2. Ingestion | `src/2_ingestion/` | Full CSV load and incremental Postgres load into Raw |
| 3. Storage | `src/3_storage/` | Bronze write-audit-publish, events build, run history records |
| 4. Transform | `src/4_transform/`, `dbt_project/` | dbt builds Silver facts, dimensions and Gold business tables |
| 5. Serving | `src/5_serving/` | Streamlit health dashboard and EDA page over Silver |
| Orchestration | `dags/` | One DAG, two branches, freshness check, retries, timeouts, Discord alerts |
| Shared | `src/0_utils/` | Colored console logger with daily files; Discord alert sender |

## DAG `stylehub_daily`

| Task | Runs | Upstream |
|---|---|---|
| `ingest` | Full load of four course tables into Raw Parquet | — |
| `bronze` | Newest Raw batch replaces the Bronze day partition | `ingest` |
| `silver` | dbt builds staging, intermediate, core marts and snapshot | `bronze` |
| `gold` | dbt builds revenue tables and runs Gold unit tests | `silver` |
| `pg_ingest` | Incremental Postgres load by `updated_at` watermark with lookback | — |
| `pg_bronze` | Changed rows land in never-expiring Bronze day partitions | `pg_ingest` |
| `pg_reconcile` | Ids in Bronze but gone from Postgres go to `pg_deleted_ids` | `pg_bronze` |
| `pg_silver` | dbt keeps newest row per id without deleted ids, SCD2 product history, cost at sale | `pg_reconcile` |
| `pg_gold` | dbt builds Buổi 5 tables, profit at sale cost, revenue by region, published monthly revenue, Gold-Silver check | `pg_silver` |
| `freshness` | Fails and alerts when a Bronze table is older than 26 hours | `gold`, `pg_gold` |

## Data layers

| Layer | Location | Rule |
|---|---|---|
| Raw | `gs://<bucket>/raw/stylehub/<table>/date=<day>/batch_id=<id>/` | Append-only Parquet with `_ingested_at`, `_source`, `_batch_id` |
| Bronze | `stylehub_bronze` | One partition per day; reruns replace, never duplicate |
| Staging | `stylehub_staging` | Views holding personal data; tables expire after seven days |
| Silver | `stylehub_silver` | Facts and dimensions; grain tested with unique and not_null |
| Gold | `stylehub_gold` | Business rules; contracts and unit tests guard published columns |
| Ops | `stylehub_ops.pipeline_runs` | One row per step attempt with rows and errors |

## Postgres incremental load

| Rule | Specification |
|---|---|
| Watermark | `updated_at` catches new rows and changed rows alike |
| Window | From Bronze watermark minus one day to data-day end |
| First run | No Bronze table yet, so read the whole table |
| Idempotency | Same watermark on rerun reads same rows, replaces partition |
| Consistency | One `REPEATABLE READ` transaction, row count checked against source |
| Volume | One read per window; the window is held in memory |
| Deletes | `pg_reconcile` compares all ids daily; `pg_deleted_ids` makes Silver drop them |
| Empty day | No changed rows writes no file and is not failure |

## Data quality checks

| Check | Where | Severity |
|---|---|---|
| Source columns match declared schema before reading rows (course tables and Postgres) | `src/2_ingestion/schema_check.py` | Error stops run |
| Rows read equal source table row count | `csv_tables.py`, `postgres_tables.py` | Error stops run |
| Bronze staging rows equal Raw file footer rows | `src/3_storage/load_bronze.py` | Error keeps partition |
| Empty Bronze day fails CSV branch loudly | `src/4_transform/run_daily.py` | Error stops run |
| Every Silver id unique and not null | dbt schema tests | Error stops run |
| Order status within the five known values | dbt `accepted_values` | Error stops run |
| Item `amount` equals `sale_price` times `quantity` | `dbt_utils.expression_is_true` on `pg_fact_order_items` | Error stops run |
| Every user country has a row in the `country_regions` seed | dbt `relationships` | Warning only |
| Gold revenue totals equal Silver revenue total | `tests/pg_gold_matches_silver.sql` | Error stops run |
| Recent `fact_events` grain without scanning 15 GB | `tests/fact_events_recent_grain.sql` | Error stops run |
| Product history has one current row, no gaps or overlaps | `tests/pg_products_history_is_continuous.sql` | Error stops run |
| Published month revenue differs from today's number | `tests/pg_published_revenue_drift.sql` | Warning only |
| Foreign keys between facts and dimensions | dbt `relationships` | Warning only |

## Serving

| Page | Content |
|---|---|
| Pipeline health | Fourteen days of step runs, failures, durations, Bronze freshness |
| EDA | Quality report, duplicates, rule checks, statistics, outliers, KPIs, correlation |

## Monitoring and alerts

| Signal | Where | Action |
|---|---|---|
| Task fails after its retry | Airflow `on_failure_callback` | Discord message with task, run, error, log link |
| Run longer than one hour | `dagrun_timeout`, DAG callback | Run fails, Discord message |
| Task longer than 30 minutes | `execution_timeout` | Task fails, then alerts |
| Bronze table older than 26 hours | `freshness` task, dashboard | Task fails, Discord message, dashboard warning |
| Pipeline BigQuery job fails anywhere | Log metric and alert policy (Terraform) | Incident in Cloud Monitoring |
| Every step attempt | `stylehub_ops.pipeline_runs` | Dashboard history |

## Security and access

| Rule | Specification |
|---|---|
| Secrets | Git-ignored `secrets/.env` locally; GitHub secrets for the workflows; Workload Identity Federation instead of key files; `SecretStr` hides passwords |
| Personal data | Names and addresses dropped; email hashed in dimensions |
| GitHub login | Workload Identity Federation tokens, no JSON keys stored |
| Apply rights | Terraform apply account usable only from `main` branch |
| Least privilege | One service account per job, dataset-level BigQuery roles |
| Raw bucket | Pipeline may create and read files, never delete |
| Cost cap | Every query billed at most 50 GB via `BQ_MAX_BYTES_BILLED` |

## Quality gates

| Gate | Tool | Rule |
|---|---|---|
| Lint and format | ruff, sqlfluff, pre-commit | Must pass before commit and in CI |
| Unit tests | pytest with fakes for GCP, Postgres, dbt | 100 percent line coverage required |
| DAG integrity | pytest inside the Airflow image | DAG loads, task order checked |
| dbt project | `dbt parse` without a warehouse connection | Must parse in CI |
| Terraform | `fmt`, `validate`, `plan` on pull requests | Plan reviewed before apply |
| Dependencies | `requirements.txt` regenerated from `uv.lock` | CI fails when they differ |

## Logging

| Component | Rule |
|---|---|
| Python | `get_logger` colors terminal only; daily plain files in `logs/custom_scripts` |
| Airflow | Task logs persist in `logs/airflow` through compose volume |
| dbt | Colored screen output, JSON file per layer in `logs/dbt` |
| Terraform | `deploy.sh` colors console, saves plain copies in `logs/infra` |

## Infrastructure layout

| Part | Path | Rule |
|---|---|---|
| Prod root | `infra/terraform/` | Applied by CD from `main`; state prefix `stylehub` |
| Dev root | `infra/terraform/envs/dev/` | Applied by hand; `_dev` datasets; state prefix `stylehub-dev` |
| Dataset module | `infra/terraform/modules/bigquery_dataset/` | Dataset plus dataset IAM, `prevent_destroy`; used by both roots |
| State moves | `infra/terraform/moved.tf` | Renames state entries into the module; delete after one apply |

## Known limits

- Terraform is applied by CD from `main`; changes made in the console are undone.
- Airflow runs on a laptop; the 02:00 UTC schedule needs it switched on.
- Product cost history starts on 2026-10-01; older sales use the first known version.
- CSV and Postgres branches build parallel Silver and Gold stacks today.
- Airflow 3 structlog colors console; custom colorlog formatter loads but unused.
