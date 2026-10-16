-- Migration for a pipeline_runs table made before the `detail` column existed.
-- Run by `python -m stylehub.setup.setup_gcp` only, never by the daily pipeline.
-- IF NOT EXISTS keeps it safe to run again.
ALTER TABLE `${project}.${ops}.pipeline_runs` ADD COLUMN IF NOT EXISTS detail STRING;
