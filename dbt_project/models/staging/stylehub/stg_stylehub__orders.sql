-- One row per order, newest snapshot; dedupe is a safety net.

WITH source AS (
  {{ latest_bronze_snapshot('orders') }}
),

latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC, _batch_id DESC) = 1
)

SELECT
  order_id,
  user_id,
  status,
  num_of_item,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(shipped_at AS TIMESTAMP) AS shipped_at,
  CAST(delivered_at AS TIMESTAMP) AS delivered_at,
  CAST(returned_at AS TIMESTAMP) AS returned_at
FROM latest
