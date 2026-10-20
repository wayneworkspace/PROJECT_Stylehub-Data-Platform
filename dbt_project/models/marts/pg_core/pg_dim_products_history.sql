-- SCD Type 2 built from Bronze, which keeps every updated_at version of a
-- product. A new version starts only when a tracked column changes (row_hash);
-- an updated_at change alone does not. Sales before the first known version
-- use that version.

WITH versions AS (
  SELECT
    id AS product_id,
    name,
    category,
    brand,
    department,
    sku,
    cost,
    retail_price,
    CAST(updated_at AS TIMESTAMP) AS updated_at,
    -- Tracked columns; TO_JSON_STRING keeps NULLs, so NULL to a value counts as a change.
    TO_HEX(MD5(TO_JSON_STRING(
      STRUCT(name, category, brand, department, sku, cost, retail_price)
    ))) AS row_hash
  FROM {{ source('stylehub_pg', 'pg_products') }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id, updated_at ORDER BY _ingested_at DESC) = 1
),

changes AS (
  SELECT *
  FROM versions
  QUALIFY
    LAG(row_hash) OVER (PARTITION BY product_id ORDER BY updated_at) IS DISTINCT FROM row_hash
)

SELECT
  -- Surrogate key of the version; the same on every rebuild, so facts can store it.
  TO_HEX(MD5(CONCAT(CAST(product_id AS STRING), '|', CAST(updated_at AS STRING)))) AS product_key,
  product_id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price,
  row_hash,
  updated_at,
  IF(ROW_NUMBER() OVER w = 1, TIMESTAMP '1970-01-01', updated_at) AS valid_from,
  COALESCE(LEAD(updated_at) OVER w, TIMESTAMP '9999-12-31') AS valid_to,
  LEAD(updated_at) OVER w IS NULL AS is_current
FROM changes
WINDOW w AS (PARTITION BY product_id ORDER BY updated_at)
