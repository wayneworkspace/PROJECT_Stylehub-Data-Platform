-- Grain: one row per customer. Gathers everything about a customer.
-- Personal data stays out of the marts: the email is replaced by a hash (still good for counting
-- and joining customers) and the exact latitude/longitude are not copied. Staging still has them.
-- A hash without a secret salt can be guessed for a known email, so this is pseudonymisation,
-- not anonymisation.

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
FROM {{ ref('stg_stylehub__users') }}
