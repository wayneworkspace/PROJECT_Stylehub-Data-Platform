-- One row per customer; email hashed (unsalted), exact location dropped.

SELECT
  id,
  TO_HEX(SHA256(LOWER(TRIM(email)))) AS email_hash,
  gender,
  age,
  country,
  state,
  city,
  traffic_source,
  created_at
FROM {{ ref('stg_pg__users') }}
