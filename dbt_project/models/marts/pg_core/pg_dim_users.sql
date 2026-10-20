-- One row per customer; email hashed (unsalted), exact location dropped.
-- Customers deleted in Postgres stay (is_deleted) so old orders still join.

SELECT
  id,
  TO_HEX(SHA256(LOWER(TRIM(email)))) AS email_hash,
  gender,
  age,
  country,
  state,
  city,
  traffic_source,
  created_at,
  is_deleted,
  deleted_at
FROM {{ ref('stg_pg__users') }}
