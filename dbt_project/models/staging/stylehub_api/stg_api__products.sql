-- One row per API product from the newest snapshot; the dedupe is a safety net.

WITH source AS (
  {{ latest_bronze_snapshot('api_products', 'stylehub_api') }}
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
  CAST(cost AS NUMERIC) AS cost,
  CAST(retail_price AS NUMERIC) AS retail_price,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest
