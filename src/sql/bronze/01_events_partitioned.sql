-- Session 1: events table (~108 million rows) partitioned by day, clustered by event_type, product_id.
-- Run by hand once (it scans the whole source table); it is not part of the daily run.
-- It reads ${bronze}.events_raw, a copy of the course events table made by
-- python -m storage.copy_events (the course dataset is in another region, so SQL cannot read it).
-- If queries by user_id are common, consider adding user_id to CLUSTER BY (see docs/DECISIONS.md).

CREATE OR REPLACE TABLE `${project}.${bronze}.events_partitioned`
PARTITION BY DATE(event_time)
CLUSTER BY event_type, product_id
AS
SELECT *
FROM `${project}.${bronze}.events_raw`;
