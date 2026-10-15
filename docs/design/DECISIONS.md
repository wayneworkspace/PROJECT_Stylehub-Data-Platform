# Design decisions

Record every decision together with real measurements. This is where you answer the interview question "why did you choose this?".

## 1. Partition and cluster for `events` (session 1)

Current setup: `PARTITION BY DATE(event_time) CLUSTER BY event_type, product_id`.

_Not measured yet. Run each query with a dry run and fill in the table._

| Query | Bytes processed | Uses partition/cluster |
|---|---|---|
| Top 10 products purchased in one week | _fill in after measuring_ | partition + cluster |
| Event count per event_type on one day | _fill in_ | partition |
| Full history of one user_id (no date filter) | _fill in_ | no |

If queries by `user_id` are common: add `user_id` to the cluster key, because BigQuery can skip blocks only when the WHERE clause uses a cluster column. Record the measurements before and after the change.

## 2. Watermark for `order_items` (session 2)

Course CSV path (the one `run_daily` uses): the CSV files have no `updated_at` column, so there is no watermark. Every run is a full load, and Silver keeps the latest row of each id (see [ROADMAP.md](ROADMAP.md), session 2).

_Postgres path (not run on a real source yet): fill in after checking whether `updated_at` of `order_items` changes when an order changes status. Pick the column and the lookback from the result._

Short README answering 3 questions: why that column and how many days of lookback; what the Raw Zone contains after a re-run and how duplicates are dropped; whether the pipeline notices when the source deletes a row.

## 3. Sync mode per table (session 4)

_Not started: Airbyte (session 4) is not set up yet. Fill in per table from ARCHITECTURE.md: one sentence of reasoning and the row count compared with the source._

## 4. Star or Snowflake (session 5)

Star by default. Move to Snowflake only when a dimension is very large, has many levels, or its attributes change often.
