-- One row per product, from the newest Bronze snapshot.

WITH source AS (
  {{ latest_bronze_snapshot('products') }}
),

latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC, _batch_id DESC) = 1
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
