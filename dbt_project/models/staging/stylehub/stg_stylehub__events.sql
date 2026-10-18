-- One row per event; kept simple so partition filters apply.

WITH source AS (
  SELECT *
  FROM {{ source('stylehub', 'events_partitioned') }}
)

SELECT
  event_id,
  user_id,
  product_id,
  event_type,
  NULLIF(category_code, 'Unknown') AS category_code,
  brand,
  ROUND(CAST(price AS NUMERIC), 2) AS price,
  user_session,
  CAST(event_time AS TIMESTAMP) AS event_time
FROM source
