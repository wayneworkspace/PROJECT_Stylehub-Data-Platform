-- One row per order status we saw (grain order_id, valid_from).
-- valid_from is when the pipeline loaded that status (_ingested_at), not the
-- source updated_at: it answers "on the day a report went out, what did we know?".
-- As-of query: valid_from <= t AND t < valid_to.

WITH loaded AS (
  SELECT
    id AS order_id,
    user_id,
    status,
    total_amount,
    DATE(created_at) AS order_date,
    CAST(updated_at AS TIMESTAMP) AS updated_at,
    _ingested_at
  FROM {{ source('stylehub_pg', 'pg_orders') }}
),

changes AS (
  -- The lookback reloads the same status; keep only the loads where it changed.
  SELECT *
  FROM loaded
  QUALIFY
    LAG(status) OVER (PARTITION BY order_id ORDER BY _ingested_at, updated_at)
    IS DISTINCT FROM status
)

SELECT
  order_id,
  user_id,
  status,
  total_amount,
  order_date,
  updated_at,
  _ingested_at AS valid_from,
  COALESCE(LEAD(_ingested_at) OVER w, TIMESTAMP '9999-12-31') AS valid_to,
  LEAD(_ingested_at) OVER w IS NULL AS is_current
FROM changes
WINDOW w AS (PARTITION BY order_id ORDER BY _ingested_at, updated_at)
