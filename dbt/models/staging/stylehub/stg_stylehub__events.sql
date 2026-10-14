-- Staging: one row per event. A view over the partitioned Bronze table (about 108 million rows).
-- Bronze events_partitioned is built once and has no duplicates, so there is no dedupe here.
-- The text 'Unknown' in category_code means "no category", so it becomes a real NULL.
-- Keep this view simple (no joins, no window functions): the filters of fact_events must still
-- reach the Bronze partitions, so a daily run does not scan the whole table.

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
