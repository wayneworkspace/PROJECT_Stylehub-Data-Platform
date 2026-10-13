-- One row per pipeline step per run. The pipeline writes it; nobody edits it by hand.
-- Grain: one row per (run_id, step).
CREATE TABLE IF NOT EXISTS `${project}.${ops}.pipeline_runs` (
  run_id STRING NOT NULL,
  step STRING NOT NULL,
  data_date DATE NOT NULL,
  status STRING NOT NULL,      -- success or failed
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP NOT NULL,
  duration_seconds FLOAT64,
  rows_loaded INT64,           -- only steps that count rows fill this in
  error STRING
)
PARTITION BY DATE(started_at)
