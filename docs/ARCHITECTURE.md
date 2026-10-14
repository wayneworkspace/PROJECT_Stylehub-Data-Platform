# Architecture

## Layers

| Layer | Where | Contents | Written by |
|---|---|---|---|
| Raw Zone | GCS `raw/stylehub/<table>/date=<date>/batch_id=<id>/` | Files exactly as fetched, append-only, with `_ingested_at`, `_source`, `_batch_id` | `src/python/ingestion/` or Airbyte |
| Bronze | BigQuery `stylehub_bronze` | Copy of the source, keeping every ingest | `src/python/storage/load_bronze.py` |
| Silver | BigQuery `stylehub_silver` | Cleaned, organized into facts and dimensions | `src/sql/silver/` |
| Gold | BigQuery `stylehub_gold` | Business tables that hold the rules | `src/sql/gold/` |

When a business rule changes, rerun from the nearest layer: edit Gold, leave Silver as is.

## Star schema (Silver)

| Table | Grain | Type |
|---|---|---|
| fact_order_items | one order item | fact |
| fact_orders | one order | fact |
| fact_shipments | one shipment | fact |
| dim_products | one product | dimension |
| dim_users | one customer | dimension |

`events` (behavior, ~108 million rows) sits in Bronze as `events_partitioned`. When it needs modeling, `fact_events` and `dim_date` will be added to Silver.

## Current Gold tables

| Table | Question it answers |
|---|---|
| daily_revenue | Revenue and order count per day (Cancelled excluded) |
| monthly_revenue_by_category | Revenue and profit by category per month |
| return_rate_by_state | Share of returned orders by state |
| avg_delivery_days_by_state | Average delivery time by state |

## Ingestion (sessions 2 and 4)

- **Python API ingestion** (`src/python/ingestion/api.py`, client in `src/python/sources/stylehub_api.py`): reads the `users` endpoint one day at a time with `created_from` and `created_to`. It sends the key in a header, reads pages until `has_more` is false, and retries 5xx errors, timeouts and rate limits with a wait that doubles. It stops at once on 400 or 401.
- **Python database ingestion** (`src/python/ingestion/database.py`): use when you need control over each step: choosing the watermark, the lookback, and the Raw path. It can load one day (incremental) or the whole table (`--full-load`). Before it writes, `src/python/ingestion/schema_check.py` compares the columns with the expected ones (see the table in that file).
- **Backfill** (`src/python/orchestration/backfill.py`): runs the steps for a range of past dates. Running the range twice adds Raw files but does not change the distinct ids.
- **Airbyte OSS** on a GCP VM (`e2-standard-4`, `asia-southeast1-b`): use for Postgres and the API (Connector Builder).

Airbyte sync modes (from session 4):

| Table | Mode | Reason |
|---|---|---|
| orders | Incremental, Append (cursor `updated_at`) | A status change adds a row, keeping every version |
| order_items | Incremental, Append (cursor chosen after checking real data) | See DECISIONS.md, section 2 |
| products | Full Refresh, Overwrite | Small table, needs a full snapshot |
| shipments | To be decided, record in DECISIONS.md | |

Operations: stop the Airbyte VM after use and restrict the port 8000 firewall rule to your own IP.

## Extension points

Every step is an independent CLI with `--date` and is safe to re-run. See [EXTENDING.md](EXTENDING.md) for how to add dbt, Airflow and Spark.
