-- Pipeline steps of the last 14 days, newest first.
SELECT
  data_date,
  step,
  status,
  started_at,
  duration_seconds,
  rows_loaded,
  error
FROM `${project}.${ops}.pipeline_runs`
WHERE started_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
ORDER BY started_at DESC
