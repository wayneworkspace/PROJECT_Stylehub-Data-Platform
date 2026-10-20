-- One row per user from the REST API, newest version.

SELECT
  id AS user_id,
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
  created_at,
  updated_at
FROM {{ ref('stg_api__users') }}
