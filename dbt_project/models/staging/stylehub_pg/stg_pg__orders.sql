-- One row per order: newest version across incremental Bronze.

WITH latest AS (
  {{ latest_pg_rows('pg_orders') }}
)

SELECT
  id AS order_id,
  user_id,
  status,
  total_amount,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(updated_at AS TIMESTAMP) AS updated_at,
  is_deleted,
  deleted_at
FROM latest
