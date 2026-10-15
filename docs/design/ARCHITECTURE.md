# Architecture

## Layers

| Layer | Where | Contents | Written by |
|---|---|---|---|
| Raw Zone | GCS `raw/stylehub/<table>/date=<date>/batch_id=<id>/` | Files exactly as fetched, append-only, with `_ingested_at`, `_source`, `_batch_id` | `src/python/ingestion/csv_tables.py` (or Postgres, API, Airbyte) |
| Bronze | BigQuery `stylehub_bronze` | Copy of the source, keeping every ingest | `src/python/storage/load_bronze.py` |
| Silver | BigQuery `stylehub_silver` | Cleaned, organized into facts and dimensions | dbt: `dbt/models/staging/`, `intermediate/`, `marts/core/` |
| Gold | BigQuery `stylehub_gold` | Business tables that hold the rules | dbt: `dbt/models/marts/reporting/` |

When a business rule changes, rerun from the nearest layer: edit Gold, leave Silver as is.

## Star schema (Silver)

| Table | Grain | Type |
|---|---|---|
| fact_order_items | one order item | fact |
| fact_orders | one order | fact |
| fact_shipments | one shipped order (built from order dates) | fact |
| fact_events | one event (view, cart, purchase) | fact |
| dim_products | one product | dimension |
| dim_users | one customer | dimension |

`events` (behavior, ~108 million rows) sits in Bronze as `events_partitioned`. It is copied from the course dataset once (that dataset is in another region) and then partitioned. `fact_events` is in Silver. `dim_date` is not built yet.

## Current Gold tables

| Table | Question it answers |
|---|---|
| daily_revenue | Revenue and order count per day (Cancelled excluded) |
| monthly_revenue_by_category | Revenue and profit by category per month |
| return_rate_by_state | Share of returned orders by state |
| avg_delivery_days_by_state | Average delivery time by state |
| daily_events_by_type | Events, users and sessions per day and event type |
| funnel_by_category | Views, cart adds and purchases per product category |

## Ingestion (sessions 2 and 4)

- **Python CSV-table ingestion** (`src/python/ingestion/csv_tables.py`): the path `run_daily` uses. It reads the course tables from the `stylehub` dataset in BigQuery, checks the columns, and writes a full Parquet file to the Raw Zone. The CSV files have no `updated_at`, so there is no watermark.
- **Python API ingestion** (`src/python/ingestion/optional/api.py`, client in `src/python/ingestion/optional/sources/stylehub_api.py`): reads the `users` endpoint one day at a time with `created_from` and `created_to`. It sends the key in a header, reads pages until `has_more` is false, and retries 5xx errors, timeouts and rate limits with a wait that doubles. It stops at once on 400 or 401.
- **Python database ingestion** (`src/python/ingestion/optional/database.py`): use when you need control over each step: choosing the watermark, the lookback, and the Raw path. It can load one day (incremental) or the whole table (`--full-load`). Before it writes, `src/python/ingestion/schema_check.py` compares the columns with the expected ones (see the table in that file).
- **Backfill**: use `airflow dags backfill` (see `deploy/airflow/README.md`). Running a range twice adds Raw files but does not change the distinct ids.
- **Airbyte OSS** on a GCP VM (`e2-standard-4`, `asia-southeast1-b`): use for Postgres and the API (Connector Builder).

Airbyte sync modes (from session 4):

| Table | Mode | Reason |
|---|---|---|
| orders | Incremental, Append (cursor `updated_at`) | A status change adds a row, keeping every version |
| order_items | Incremental, Append (cursor chosen after checking real data) | See DECISIONS.md, section 2 |
| products | Full Refresh, Overwrite | Small table, needs a full snapshot |
| shipments | To be decided, record in DECISIONS.md | |

Operations: stop the Airbyte VM after use and restrict the port 8000 firewall rule to your own IP.

## Reference tables

These tables were moved here from the README.

### Code layers

| Layer | Responsibility | Files |
|---|---|---|
| Ingestion | Read the course tables. Write raw Parquet files. Nothing else. | `src/python/ingestion/csv_tables.py` (used by the pipeline). `database.py` (Postgres) and `api.py` are kept for a live source. |
| Load | Load the latest Raw batch of each day into Bronze. Build the big `events` table once. | `src/python/storage/load_bronze.py`, `events_bronze.py`, `copy_events.py` |
| Transform | Build Silver and Gold with dbt. dbt tests are the data checks. | `src/python/transform/run_dbt.py`, `dbt/` |
| Table setup | Run the SQL files of the Bronze layer (partitioned events). | `src/python/transform/run_sql.py`, `src/sql/` |
| Runner | Run all steps for one date. | `src/python/orchestration/run_daily.py` |
| Config | Read environment variables. Fill `${project}` and similar names in SQL. | `src/python/common/config.py` |

### Data layers

| Layer | Where | Contents |
|---|---|---|
| Raw Zone | GCS: `raw/stylehub/<table>/date=<date>/batch_id=<id>/` | Files as fetched. Each has `_ingested_at`, `_source` and `_batch_id`. |
| Bronze | BigQuery: `stylehub_bronze` | A copy of the source. One snapshot per day. |
| Silver | BigQuery: `stylehub_silver` | One latest row per id, with correct types. Built as a star schema. |
| Gold | BigQuery: `stylehub_gold` | Business tables that hold the rules. |

### Silver and Gold tables

| Table | Layer | What one row means |
|---|---|---|
| `fact_order_items` | Silver | One item in an order |
| `fact_orders` | Silver | One order |
| `fact_shipments` | Silver | One shipped order |
| `fact_events` | Silver | One event (view, cart, purchase). About 108 million rows. Incremental. |
| `dim_products` | Silver | One product |
| `dim_users` | Silver | One customer |
| `daily_revenue` | Gold | Orders and revenue for one day (no Cancelled orders) |
| `monthly_revenue_by_category` | Gold | Revenue and profit for one category in one month |
| `return_rate_by_state` | Gold | Share of returned orders in one state |
| `avg_delivery_days_by_state` | Gold | Average delivery time in one state |
| `daily_events_by_type` | Gold | Events, users and sessions for one day and one event type |
| `funnel_by_category` | Gold | Views, cart adds and purchases for one product category |

### dbt folders

The dbt folders follow the dbt Labs layout. The datasets and the step names keep the Silver and Gold names.

| dbt folder | Models | Dataset | Built by step |
|---|---|---|---|
| `models/staging/stylehub/` | 5 views `stg_stylehub__*`. Latest row per id, types cast. Only these call `source()` | `stylehub_silver` | `silver` |
| `models/intermediate/` | 2 views `int_*`: items with product cost, orders with item totals | `stylehub_silver` | `silver` |
| `models/marts/core/` | 6 tables: `dim_products`, `dim_users`, `fact_orders`, `fact_order_items`, `fact_shipments`, `fact_events` | `stylehub_silver` | `silver` |
| `models/marts/reporting/` | 6 tables, the Gold business tables | `stylehub_gold` | `gold` |

Tags, materialization and dataset are set per folder in `dbt/dbt_project.yml`. Each folder has its own `_<folder>__models.yaml`.

### Key design decisions (details)

| Decision | How it works |
|---|---|
| Raw Zone is append-only | Each run writes a new file under a new `batch_id`. Nothing is overwritten. |
| Bronze keeps one batch per day | Running a day twice replaces that day's batch, so rows are not doubled. Each day stays as its own snapshot. Silver keeps the newest row of each id. |
| Latest row per id | Silver keeps the newest version of each id with `QUALIFY ROW_NUMBER()`. |
| Full load for CSV | The course CSV files have no `updated_at`, so every run reads whole tables. Silver keeps the latest row of each id. |
| Lookback window | Only for the Postgres path. It reads one extra day before the target date. |
| Rules live in Gold | Gold drops `Cancelled` orders. If the rule changes, rebuild Gold only. |
| Grain comes first | Each Silver file states its grain at the top. A check compares row count with distinct id count. |
| Partition and cluster | `events_partitioned` is split by day and clustered by `event_type` and `product_id`. It is built once; the course `events` table is in the US, so it is copied to Bronze first. |
| Incremental events | `fact_events` rebuilds the newest 3 days (`insert_overwrite` by `event_date`, variable `events_lookback_days`). Use `--full-refresh` to rebuild all. |
| Airflow operators | `ExternalPythonOperator` runs the Python steps (ingest, bronze) in a separate environment. `BashOperator` runs the dbt steps (silver, gold) through the CLI. `EmptyOperator` marks the start and the end. `PythonOperator` is not used, because Airflow pins library versions that clash with the pipeline. |
| Logic stays in SQL | SQL files hold the business logic. Python only runs them. |
| CTEs, no subqueries | Every SQL file uses CTEs. A test fails if it finds a subquery. |

## Extension points

Every step is an independent CLI with `--date` and is safe to re-run. See [EXTENDING.md](EXTENDING.md) for how to add dbt, Airflow and Spark.
