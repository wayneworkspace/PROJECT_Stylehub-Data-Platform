-- Last change of each daily Bronze table, from free metadata.
-- Postgres changes every day, so its two busiest tables are checked too.
-- shortcut: pg_orders and pg_order_items left out while the Postgres branch is paused
-- (PG_ENABLED in dags/main_etl_dag.py); add them back when it runs again.
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
