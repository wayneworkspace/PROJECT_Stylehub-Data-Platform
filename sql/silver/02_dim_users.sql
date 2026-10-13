-- Grain: one row per customer. Gathers everything about a customer (session 5, exercise 2).
-- Check the column names against the real schema before running.

CREATE OR REPLACE TABLE `${project}.${silver}.dim_users` AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.users`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
)
SELECT
  id,
  email,
  country,
  state,
  city,
  street_address,
  latitude,
  longitude,
  traffic_source
FROM latest;
