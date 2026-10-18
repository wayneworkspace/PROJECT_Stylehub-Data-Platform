-- One row per customer, newest snapshot; 'null' city becomes NULL.

WITH source AS (
  {{ latest_bronze_snapshot('users') }}
),

latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC, _batch_id DESC) = 1
)

SELECT
  id,
  email,
  gender,
  age,
  country,
  state,
  NULLIF(city, 'null') AS city,
  latitude,
  longitude,
  traffic_source,
  CAST(created_at AS TIMESTAMP) AS created_at
FROM latest
