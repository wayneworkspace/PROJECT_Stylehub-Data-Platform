-- Grain of fact_events: event_id is not NULL and appears once, in the recent window only.
-- A daily run changes only that window (see macros/events_test_window.sql), so the older
-- partitions are not scanned again. After a --full-refresh check the whole table with:
--   dbt test --select fact_events_recent_grain --vars "{events_test_full: true}"
-- Any row returned here is a failure.
{{ config(tags=['silver']) }}

WITH recent AS (
  SELECT event_id
  FROM {{ ref('fact_events') }}
  WHERE event_date >= {{ events_test_window() }}
)

SELECT
  event_id,
  COUNT(*) AS n_rows
FROM recent
GROUP BY event_id
HAVING
  event_id IS NULL
  OR COUNT(*) > 1
