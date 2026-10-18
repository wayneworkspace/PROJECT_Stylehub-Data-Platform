-- One row per customer; names, street and postal code are dropped.

WITH latest AS (
  {{ latest_pg_rows('pg_users') }}
)

SELECT
  id,
  email,
  gender,
  age,
  country,
  state,
  city,
  latitude,
  longitude,
  traffic_source,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest
