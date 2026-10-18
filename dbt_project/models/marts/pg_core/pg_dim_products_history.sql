-- SCD Type 2 built from Bronze, which keeps every updated_at version of a
-- product. Sales before the first known version use that version.

WITH versions AS (
  SELECT
    id AS product_id,
    name,
    category,
    brand,
    department,
    cost,
    retail_price,
    CAST(updated_at AS TIMESTAMP) AS updated_at
  FROM {{ source('stylehub_pg', 'pg_products') }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id, updated_at ORDER BY _ingested_at DESC) = 1
)

SELECT
  product_id,
  name,
  category,
  brand,
  department,
  cost,
  retail_price,
  updated_at,
  IF(ROW_NUMBER() OVER w = 1, TIMESTAMP '1970-01-01', updated_at) AS valid_from,
  COALESCE(LEAD(updated_at) OVER w, TIMESTAMP '9999-12-31') AS valid_to,
  LEAD(updated_at) OVER w IS NULL AS is_current
FROM versions
WINDOW w AS (PARTITION BY product_id ORDER BY updated_at)
