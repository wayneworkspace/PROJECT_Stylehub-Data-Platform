-- When each daily Bronze table was loaded last. Grain: one row per table.
-- events is built once and never reloaded, so it is not here.
WITH loads AS (
  SELECT 'orders' AS table_name, MAX(_ingested_at) AS last_loaded_at
  FROM `${project}.${bronze}.orders`
  UNION ALL
  SELECT 'order_items' AS table_name, MAX(_ingested_at) AS last_loaded_at
  FROM `${project}.${bronze}.order_items`
  UNION ALL
  SELECT 'products' AS table_name, MAX(_ingested_at) AS last_loaded_at
  FROM `${project}.${bronze}.products`
  UNION ALL
  SELECT 'users' AS table_name, MAX(_ingested_at) AS last_loaded_at
  FROM `${project}.${bronze}.users`
)

SELECT
  table_name,
  last_loaded_at,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), last_loaded_at, HOUR) AS hours_old
FROM loads
ORDER BY table_name
