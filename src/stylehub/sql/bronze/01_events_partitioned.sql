-- Events table (~108 million rows) partitioned by day,
-- clustered by event_type, product_id.
-- One-time set-up (it scans the whole source table): python -m stylehub.bronze.events_bronze.
-- It is NOT part of the daily run. The daily Bronze step only checks that this table exists.
-- events_bronze deletes events_raw after this table is built.
-- It reads ${bronze}.events_raw, a copy of the course events table made by
-- python -m stylehub.bronze.copy_events (the course dataset is in another region, so SQL
-- cannot read it).
-- Events skip the Raw Zone (15 GB, never changes), so the 3 metadata columns are added here.
-- If queries by user_id are common, consider adding user_id to CLUSTER BY.

CREATE OR REPLACE TABLE `${project}.${bronze}.events_partitioned`
PARTITION BY DATE(event_time)
CLUSTER BY event_type, product_id
AS
SELECT
  *,
  CURRENT_TIMESTAMP() AS _ingested_at,
  'course_bigquery' AS _source,
  'events_bootstrap' AS _batch_id
FROM `${project}.${bronze}.events_raw`;
