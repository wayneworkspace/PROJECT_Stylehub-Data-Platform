-- One row per order item: newest version across incremental Bronze.

WITH latest AS (
  {{ latest_pg_rows('pg_order_items') }}
)

SELECT
  id,
  order_id,
  product_id,
  sale_price,
  quantity,
  amount,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest
