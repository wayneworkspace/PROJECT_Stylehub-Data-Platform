# Limitations

This is the complete list. The README shows only the biggest ones.

| Area | Limitation |
|---|---|
| Testing | Run `uv run pytest` for the unit tests. dbt (the old 12-model layout), the Raw and Bronze steps and an earlier version of the Airflow DAG have run on a real BigQuery project. A later full `run_daily` run on real BigQuery passed 47 checks in silver and 11 in gold, and the incremental `fact_events` scanned about 1.9 GiB. The new DAG operators, the Bronze load-then-delete logic, the retry helper, the merged compose file and the freshness check have not run there yet. The Postgres integration tests need the Docker Postgres. Gold numbers were not checked by hand against the CSV files. |
| Schema | `EXPECTED_SCHEMAS` covers the four course tables as BigQuery detected them. New columns only give a warning. `shipments` has no source, so `fact_shipments` is built from order dates (shipped orders only). |
| Setup scripts | `setup_gcp` and `load_csv` have run on a real project. BigQuery detects column types from the CSV, so check them again if the files change. |
| Sources | The pipeline reads the course tables that `load_csv` put in BigQuery. The Postgres and API code is kept but has not run on real sources, and `run_daily` does not call it. |
| Watermark | Not used for CSV data (no `updated_at`). Every run reads whole tables. |
| Deletes | The pipeline cannot see rows that the source deletes. |
| Scheduling | Airflow runs the DAG once a day. Each task retries once after 5 minutes. dbt also retries a BigQuery job that fails for a short time, up to 3 times (`job_retries` in `dbt/profiles.yml`). After that, a failed step stops the run until the next day or a manual run. |
| Logging | `run_daily` uses `logging`. The ingestion, Bronze and SQL scripts still use `print` when you run them alone. |
| Run history | Only `run_daily` writes to `pipeline_runs`. If BigQuery is down, the row waits in `logs/pipeline_runs_pending.jsonl` and goes with the next row. In a throwaway container that file is lost with the container. Only the Bronze step counts rows. |
| Alerts | One Discord message per failed step. `check_freshness` (a GitHub Actions schedule) alerts when no good run happened in 26 hours. It needs a one-time setup and has not run yet. |
| Retries in Python | `retry.py` retries short BigQuery and GCS errors up to 4 times (waits of about 2, 4 and 8 seconds). Permission, missing table and bad SQL errors fail at once. It is tested with fakes only. |
| VM | Airflow runs on a laptop in Docker. It has not run on a GCP VM yet. |
| Docker | CD signs in with Workload Identity Federation and pushes the image to Artifact Registry. A run on GitHub was green. The image has not run on a VM yet. |
| Rebuilds | Silver and Gold tables are rebuilt in full on each run, except `fact_events`, which is incremental. |
| Events | `fact_events` rebuilds the newest 3 days (`events_lookback_days`), so late events inside that window are kept. Later ones are missed until a `--full-refresh`. The first run (or `--full-refresh`) scans about 13 GB. There is no `dim_date` yet. The event dates (2019) do not overlap the order dates (2024 and later). |
| Bronze copies | Each new day adds one snapshot of every table. `events_raw` (a 15 GB copy) stays in Bronze until you delete it. |
| CI | CI has run on GitHub with all jobs green, including `dbt parse`. |
| Service accounts | The roles for one account per job are designed in `docs/ops/DEPLOY_VM.md`. The keys are not created. One key does everything now. |
| Backups | None. |
| Dependencies | `uv.lock` pins exact versions. Update them on purpose with `uv lock --upgrade`. |
| Scale | A learning project that uses a course dataset. Do not use it for real business reports. |
