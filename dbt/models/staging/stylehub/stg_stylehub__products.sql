-- Staging: one row per product, the latest version of each id in Bronze.

WITH source AS (
  SELECT *
  FROM {{ source('stylehub', 'products') }}
),
latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
)
SELECT
  id,
  name,
  category,
  brand,
  department,
  sku,
  ROUND(CAST(cost AS NUMERIC), 2) AS cost,
  ROUND(CAST(retail_price AS NUMERIC), 2) AS retail_price
FROM latest
