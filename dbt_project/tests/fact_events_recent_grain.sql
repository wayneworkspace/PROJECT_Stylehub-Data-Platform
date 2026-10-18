-- fact_events grain: event_id unique and not NULL, recent days.
-- Any row returned here is a failure.
{{ config(tags=['events']) }}

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
