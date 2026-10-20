-- One row per API user: newest version across the incremental Bronze partitions.
-- The API never reports deletes, so a user deleted at the source stays here.

WITH latest AS (
  SELECT *
  FROM {{ source('stylehub_api', 'api_users') }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _ingested_at DESC) = 1
)

SELECT
  id,
  first_name,
  last_name,
  email,
  age,
  gender,
  state,
  street_address,
  postal_code,
  city,
  country,
  latitude,
  longitude,
  traffic_source,
  CAST(created_at AS TIMESTAMP) AS created_at,
  CAST(updated_at AS TIMESTAMP) AS updated_at
FROM latest
