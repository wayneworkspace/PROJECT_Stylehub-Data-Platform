-- Staging: one row per customer, the latest version of each id in Bronze.
-- The CSV holds the text 'null' in some city values; it becomes a real NULL here.

WITH source AS (
  SELECT *
  FROM {{ source('stylehub', 'users') }}
),
latest AS (
  SELECT *
  FROM source
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
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
