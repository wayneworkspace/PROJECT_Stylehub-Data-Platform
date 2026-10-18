-- Last change of each daily Bronze table, from free metadata.
-- last_modified_time also moves when an old partition expires.
WITH bronze_tables AS (
  SELECT
    table_id AS table_name,
    TIMESTAMP_MILLIS(last_modified_time) AS last_loaded_at
  FROM `${project}.${bronze}.__TABLES__`
  WHERE table_id IN ('orders', 'order_items', 'products', 'users')
)

SELECT
  table_name,
  last_loaded_at,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), last_loaded_at, HOUR) AS hours_old
FROM bronze_tables
ORDER BY table_name
