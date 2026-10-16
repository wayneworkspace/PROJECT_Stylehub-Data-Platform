# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `SchemaError: ... the source schema changed` | A column is missing or has another type. Read the message, then fix `EXPECTED_SCHEMAS` in `src/stylehub/ingestion/schema_check.py` or the SQL. Use `--on-schema-change absorb` only on purpose. |
| `ConfigError: GCP_PROJECT_ID is not set` | `secrets/.env` is missing or incomplete. Copy `.env.example` to `secrets/.env` and fill it in. |
| `403` or "permission denied" | The service account lacks a role. Add the roles listed in the [prerequisites table](GETTING_STARTED.md#prerequisites). |
| `Not found: Dataset ...` | A dataset does not exist, or it is in another region than the query. Create the dataset, or check its location. |
| `Dataset ... was not found in location ...` | A query reads one region and writes to another. For `events`, run `python -m stylehub.bronze.events_bronze`. |
| `Provided Schema does not match Table ... Cannot add fields` | An old Bronze table has other columns. If it holds no data you need, delete it in BigQuery and run the bronze step again. |
| `DefaultCredentialsError` in a `python -c` command | Set `$env:GOOGLE_APPLICATION_CREDENTIALS` in that PowerShell window. `run_daily` reads it from `secrets/.env` itself. |
| `cannot import name 'storage' from 'google.cloud'` | The `.venv` is damaged, often by OneDrive. Run `uv sync --extra dev --extra dbt --reinstall`. |
| `load_bronze` says no files match | No Raw files exist for that table and date. Run the ingest step first. |
| "Unrecognized name" in a dbt model | The model used a wrong column name. Check the real columns in `INFORMATION_SCHEMA.COLUMNS` and edit the model. |
| `dbt` is not found | Run through `uv run`, or `uv sync --extra dbt` first. `run_dbt` looks for `dbt` on the PATH. |
| Bronze row count grows on a new day | Each day adds one full snapshot. This is by design. Re-running the same day does not add rows. BigQuery deletes snapshots older than 30 days. Silver reads only the newest one. |
| `RuntimeError: events_partitioned is missing in Bronze` | The one-time events build did not run. Run `uv run python -m stylehub.bronze.events_bronze`. |
| `RuntimeError: bronze orders: no Raw file for <date>` | The ingest step did not write a file for that date. Run `--from-step ingest --to-step ingest` for it, then bronze. |
| `RowCountMismatch: ... the source had N rows but the file holds M` | The Parquet file in the Raw Zone lost rows after it was extracted. Do not load it: run the ingest step again for that date. |
| `SchemaError: ... the source table changed` (before any row is read) | The columns of the source table in BigQuery changed. Read the message, fix `EXPECTED_SCHEMAS` and the staging models, or run with `--on-schema-change absorb` on purpose. |
| `no column named detail` when the pipeline records a run | `pipeline_runs` is older than the `detail` column. The daily pipeline no longer changes tables: run `uv run python -m stylehub.setup.setup_gcp` once. |
| `RowCountMismatch: ... Raw file has N rows but Bronze got M` | The load into BigQuery did not take every row. The day's partition was NOT changed: the bad load waits in `stylehub_bronze._stg_<table>` so you can look at it. Run the bronze step again for that date (it empties the staging table first). If it repeats, look at the load job in the BigQuery console. |
| `bronze_snapshot_not_shrinking` fails in the silver step | The newest Bronze snapshot of a table has under 90% of the rows of the one before. Silver was not rebuilt. Check the source, run ingest and bronze again, or set `bronze_min_snapshot_ratio` on purpose if the table really got smaller. |
| The `freshness` workflow says the pipeline did not run, but Airflow looks green | It checks that all 4 steps succeeded for one data date AND that every Bronze table was loaded lately. Look at `pipeline_runs` (the `detail` column shows rows per table) for the step that is missing. |
| `Bronze table ... has no partition` (from dbt) | Every Bronze snapshot is gone (expired or never loaded). Run the ingest and bronze steps first. |
| `Query exceeded limit for bytes billed` | A query tried to scan more than `BQ_MAX_BYTES_BILLED` (50 GB). Find out why before you raise the limit. |
| `docker compose up` starts nothing | Every service has a profile. Add `--profile airflow` or `--profile pipeline`. |
| The Airflow code does not show my change | The code is inside the image now. Add `--build` to the `up` command. |
| A manual `dbt build` created datasets named `dbt_...` | That is the dbt `dev` target, on purpose. The pipeline uses `prod`. Delete the `dbt_` datasets when you are done. |
| `airflow-init` stops with "set AIRFLOW_ADMIN_PASSWORD in secrets/.env" | You forgot `--env-file secrets/.env`, or an `AIRFLOW_` value in that file is empty. |
| A commit fails and files changed | A pre-commit hook fixed them, for example trailing spaces. Run `git add` again and commit again. |
| A commit is blocked by gitleaks | It found something that looks like a key. Remove the secret first. If it was a real key, rotate it. |
| The bronze step fails on a table made by an older version (an error about a partition or about `$` on a table that is not partitioned) | Bronze tables are now partitioned by day and each day is loaded into its own partition. An old table is not partitioned, so drop the four Bronze tables once. Raw keeps every day, so nothing is lost: run the bronze step again for each day you want, for example `foreach ($t in 'orders','order_items','products','users') { bq rm -f -t "$($env:GCP_PROJECT_ID):stylehub_bronze.$t" }` and then `uv run python -m stylehub.orchestration.run_daily --date 2026-10-01 --from-step bronze --to-step bronze`. |
| dbt says a contract failed: "This model has an enforced contract that failed" | A Gold column has another name or type than the `data_type` in `_reporting__models.yaml`. The message lists both. Fix the yaml if the SQL is right, or the SQL if the promise is right. |
| A dbt unit test fails in the gold step | The SQL no longer does what the rule says, or the test rows are wrong. Run only the unit tests: `uv run dbt test --project-dir dbt --profiles-dir dbt --select test_type:unit` (set `GCP_PROJECT_ID` first). The message shows expected and actual rows. |
| Airflow tasks fail with "Invalid auth token" or 401 | The API server and the scheduler use different `AIRFLOW_SECRET_KEY` values, or one was started before you set it. Set one value in `secrets/.env` and run `up -d --force-recreate`. |
| Airflow 3 web page does not accept the password | The password file is written when the API server starts. After changing `AIRFLOW_ADMIN_PASSWORD`, run `docker compose --env-file secrets/.env --profile airflow up -d --force-recreate airflow-apiserver`. |
| `terraform plan` says a resource "already exists" | It was made before by `setup_gcp` or `gcloud`. Import it once, see [TERRAFORM.md](TERRAFORM.md). |
