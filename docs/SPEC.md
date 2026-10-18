# StyleHub Data Platform Specification

## Scope

| Item | Specification |
|---|---|
| Purpose | Daily ELT turns StyleHub shop data into tested BigQuery tables |
| Sources | Course BigQuery tables and read-only course Postgres database |
| Destination | GCS Raw Zone plus BigQuery Bronze, Silver, Gold datasets |
| Schedule | Airflow runs both branches daily at 02:00 UTC |
| Consumers | Analysts read Gold; Streamlit shows health and EDA |
| Environment | Local Docker today; one GCP project, asia-southeast1 region |

## Pipeline stages

| Stage | Code | Responsibility |
|---|---|---|
| 1. Sources | `src/1_source/` | Settings, GCP and Postgres clients, retry, CSV upload |
| 2. Ingestion | `src/2_ingestion/` | Full CSV load and incremental Postgres load into Raw |
| 3. Storage | `src/3_storage/` | Bronze write-audit-publish, events build, run history records |
| 4. Transform | `src/4_transform/`, `dbt_project/` | dbt builds Silver facts, dimensions and Gold business tables |
| 5. Serving | `src/5_serving/` | Streamlit health dashboard and EDA page over Silver |
| Orchestration | `dags/` | One DAG, two branches, retries and two-hour task timeout |
| Shared | `src/utils/logger.py` | One colored console logger with plain daily files |

## DAG `stylehub_daily`

| Task | Runs | Upstream |
|---|---|---|
| `ingest` | Full load of four course tables into Raw Parquet | — |
| `bronze` | Newest Raw batch replaces the Bronze day partition | `ingest` |
| `silver` | dbt builds staging, intermediate, core marts and snapshot | `bronze` |
| `gold` | dbt builds revenue tables and runs Gold unit tests | `silver` |
| `pg_ingest` | Incremental Postgres load by `updated_at` watermark with lookback | — |
| `pg_bronze` | Changed rows land in never-expiring Bronze day partitions | `pg_ingest` |
| `pg_silver` | dbt keeps newest row per id, checks item amounts | `pg_bronze` |
| `pg_gold` | dbt builds Buổi 5 business tables and Gold-Silver check | `pg_silver` |

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
| Volume | Chunks of 100,000 rows keep memory flat on big tables |
| Deletes | Source deletes stay in Bronze; needs full compare or CDC |
| Empty day | No changed rows writes no file and is not failure |

## Data quality checks

| Check | Where | Severity |
|---|---|---|
| Source columns match declared schema before reading rows | `src/2_ingestion/schema_check.py` | Error stops run |
| Rows read equal source table row count | `csv_tables.py`, `postgres_tables.py` | Error stops run |
| Bronze staging rows equal Raw file footer rows | `src/3_storage/load_bronze.py` | Error keeps partition |
| Empty Bronze day fails CSV branch loudly | `src/4_transform/run_daily.py` | Error stops run |
| Every Silver id unique and not null | dbt schema tests | Error stops run |
| Order status within the five known values | dbt `accepted_values` | Error stops run |
| Item `amount` equals `sale_price` times `quantity` | `tests/pg_order_items_amount_matches.sql` | Error stops run |
| Gold revenue totals equal Silver revenue total | `tests/pg_gold_matches_silver.sql` | Error stops run |
| Recent `fact_events` grain without scanning 15 GB | `tests/fact_events_recent_grain.sql` | Error stops run |
| Foreign keys between facts and dimensions | dbt `relationships` | Warning only |

## Serving

| Page | Content |
|---|---|
| Pipeline health | Fourteen days of step runs, failures, durations, Bronze freshness |
| EDA | Quality report, duplicates, rule checks, statistics, outliers, KPIs, correlation |

## Security and access

| Rule | Specification |
|---|---|
| Secrets | Only in git-ignored `secrets/.env`; `SecretStr` hides passwords |
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

## Known limits

- Terraform plan verified against project; first apply needs project Owner.
- Old service accounts and `dbt_ci_*` datasets remain until removed manually.
- Gold profit uses today's product cost, not cost at sale.
- CSV and Postgres branches build parallel Silver and Gold stacks today.
- Airflow 3 structlog colors console; custom colorlog formatter loads but unused.
