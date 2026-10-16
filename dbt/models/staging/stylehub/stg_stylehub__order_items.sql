-- Staging: one row per order item (one unit sold), from the NEWEST Bronze snapshot only.

WITH source AS (
  {{ latest_bronze_snapshot('order_items') }}
),

latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC, _batch_id DESC) = 1
)

SELECT
  id,
  order_id,
  user_id,
  product_id,
  status,
  ROUND(CAST(sale_price AS NUMERIC), 2) AS sale_price,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(shipped_at AS TIMESTAMP) AS shipped_at,
  CAST(delivered_at AS TIMESTAMP) AS delivered_at,
  CAST(returned_at AS TIMESTAMP) AS returned_at
FROM latest
