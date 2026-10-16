-- Grain of the Gold tables that have more than one key column (a unique test needs one column).
-- Any row returned here is a failure: the same key appears twice.
{{ config(tags=['gold']) }}

WITH keys AS (
  SELECT
    'monthly_revenue_by_category' AS table_name,
    CONCAT(CAST(month AS STRING), '|', category) AS grain_key
  FROM {{ ref('monthly_revenue_by_category') }}
  UNION ALL
  SELECT
    'return_rate_by_state' AS table_name,
    COALESCE(state, '<unknown>') AS grain_key
  FROM {{ ref('return_rate_by_state') }}
  UNION ALL
  SELECT
    'avg_delivery_days_by_state' AS table_name,
    COALESCE(state, '<unknown>') AS grain_key
  FROM {{ ref('avg_delivery_days_by_state') }}
  UNION ALL
  SELECT
    'daily_events_by_type' AS table_name,
    CONCAT(CAST(event_date AS STRING), '|', event_type) AS grain_key
  FROM {{ ref('daily_events_by_type') }}
)

SELECT
  table_name,
  grain_key,
  COUNT(*) AS n_rows
FROM keys
GROUP BY table_name, grain_key
HAVING COUNT(*) > 1
