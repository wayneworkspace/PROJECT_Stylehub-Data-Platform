-- Staging: one row per order, the latest version of each order_id in Bronze. Cast types only.
-- Bronze keeps one snapshot per day, so the same order_id can appear in many days.

WITH source AS (
  SELECT *
  FROM {{ source('stylehub', 'orders') }}
),
latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC) = 1
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
