-- One row per API product, newest snapshot; dedupe is a safety net.

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
  title,
  category,
  brand,
  CAST(price AS NUMERIC) AS price,
  CAST(discount_percentage AS NUMERIC) AS discount_percentage,
  rating,
  stock,
  availability_status,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest
