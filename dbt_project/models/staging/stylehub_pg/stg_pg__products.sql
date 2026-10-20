-- One row per product: newest version across incremental Bronze.

WITH latest AS (
  {{ latest_pg_rows('pg_products') }}
)

SELECT
  id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price,
  CAST(updated_at AS TIMESTAMP) AS updated_at,
  is_deleted,
  deleted_at
FROM latest
