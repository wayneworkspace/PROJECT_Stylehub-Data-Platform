-- One-time build of Bronze events (~108M rows), run by events_bronze.
-- Reads the events_raw copy; adds the three Raw metadata columns.

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
