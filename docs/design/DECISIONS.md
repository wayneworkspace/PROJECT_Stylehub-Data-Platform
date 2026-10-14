# Design decisions

Record every decision together with real measurements. This is where you answer the interview question "why did you choose this?".

## 1. Partition and cluster for `events` (session 1)

Current setup: `PARTITION BY DATE(event_time) CLUSTER BY event_type, product_id`.

| Query | Bytes processed | Uses partition/cluster |
|---|---|---|
| Top 10 products purchased in one week | _fill in after measuring_ | partition + cluster |
| Event count per event_type on one day | _fill in_ | partition |
| Full history of one user_id (no date filter) | _fill in_ | no |

If queries by `user_id` are common: add `user_id` to the cluster key, because BigQuery can skip blocks only when the WHERE clause uses a cluster column. Record the measurements before and after the change.

## 2. Watermark for `order_items` (session 2)

_Fill in after checking: when an order changes status, does `updated_at` of its `order_items` change? Pick the column and the lookback from the result._

Short README answering 3 questions: why that column and how many days of lookback; what the Raw Zone contains after a re-run and how duplicates are dropped; whether the pipeline notices when the source deletes a row.

## 3. Sync mode per table (session 4)

_Fill in per table from ARCHITECTURE.md: one sentence of reasoning and the row count compared with the source._

## 4. Star or Snowflake (session 5)

Star by default. Move to Snowflake only when a dimension is very large, has many levels, or its attributes change often.
