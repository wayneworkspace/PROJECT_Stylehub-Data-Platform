# Run the pipeline end to end

This page walks you through one full run, from a fresh clone to checked Gold tables. It follows what was run on a real BigQuery project. Do the steps in order. Each step says what you should see.

> [!IMPORTANT]
> - Never commit `secrets/`, `.env`, key files, passwords or the raw CSV files.
> - The Postgres and API code paths have not run on real sources. This page uses the course CSV files.
> - Stop Airflow and any VM when you are done. They cost battery or money.

## The path in one picture

```
data/raw_data/*.csv
   -> storage.setup.load_csv        -> BigQuery dataset `stylehub` (the course tables)
   -> ingestion.csv_tables    -> Raw Zone on GCS (Parquet + _ingested_at, _source, _batch_id)
   -> storage.load_bronze     -> Bronze (latest batch of the day)         + events_partitioned (built once)
   -> dbt silver              -> Silver (tests run)
   -> dbt gold                -> Gold (tests run)
```

`orchestration.run_daily` runs the last four arrows for one date. Airflow runs the same four steps.

## Step 1. Get the code and install packages

```powershell
git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform.git
cd PROJECT_Stylehub-Data-Platform
uv sync --extra dev --extra dbt
```

If a later command says `cannot import name 'storage' from 'google.cloud'`, the `.venv` is damaged (OneDrive often does this). Run `uv sync --extra dev --extra dbt --reinstall`.

## Step 2. Fill in `secrets\.env`

```powershell
mkdir secrets
copy .env.example secrets\.env
```

Set at least `GCP_PROJECT_ID`, `GCS_BUCKET`, `GCP_LOCATION` and `GOOGLE_APPLICATION_CREDENTIALS` (the key file in `secrets\`). The `PG_*` and API values are only for the optional Postgres and API paths.

## Step 3. Run the tests

```powershell
uv run ruff check .
uv run pytest -q
```

You should see ruff pass and all tests pass (a few are skipped or deselected on purpose).

## Step 4. Create the bucket and the datasets

```powershell
uv run python -m storage.setup.setup_gcp --dry-run
uv run python -m storage.setup.setup_gcp
```

This creates the bucket and the datasets `stylehub_bronze`, `stylehub_silver`, `stylehub_gold` and `stylehub_ops`.

## Step 5. Load the course CSV files

Put the five CSV files in `data/raw_data/`.

```powershell
uv run python -m storage.setup.load_csv --file data/raw_data/orders.csv
uv run python -m storage.setup.load_csv
```

`events.csv` is about 16 GB, so uploading it takes a long time. The four small files are quick. After this, the dataset `stylehub` holds `orders`, `order_items`, `products`, `users` and `events`.

> [!NOTE]
> `stylehub` may be created in a different region (for example US) than the Bronze datasets. This is why `events` needs a copy step. The pipeline handles it for you.

## Step 6. Run the whole pipeline

```powershell
uv run python -m orchestration.run_daily --date 2026-10-01
```

| Step | What happens | What you should see |
|---|---|---|
| `ingest` | Reads the four small tables, checks columns, writes Parquet to the Raw Zone | One line per table with the row count, for example `orders ...: 125031 rows` |
| `bronze` | Builds `events_partitioned` if it is missing, then loads the latest Raw batch of the day | `orders: 125031 rows`, and so on |
| `silver` | dbt builds 13 models (5 staging views, 2 intermediate views, 6 core tables) and runs their tests | `Done. PASS=... ERROR=0` |
| `gold` | dbt builds the 6 reporting tables and runs their tests | `Done. PASS=... ERROR=0` |

The first run takes longer because it copies and partitions `events`. Later runs skip that. `fact_events` is incremental: only the newest 3 days are rebuilt. The first silver run scans about 13 GB. To rebuild all of it, run `dbt build --full-refresh --select fact_events` inside `dbt/`.

To run only some steps:

```powershell
uv run python -m orchestration.run_daily --date 2026-10-01 --from-step silver --to-step gold
```

## Step 7. Look at the results

Silver should have the same row counts as the tables you loaded: `fact_orders` 125,031, `fact_order_items` 180,835, `dim_products` 29,120, `dim_users` 100,000. `fact_shipments` is smaller (only shipped orders). `fact_events` has about 108 million rows.

To list the tables from PowerShell:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "secrets\<your-key>.json"
uv run python -c "from google.cloud import bigquery; c=bigquery.Client(); [print(d, t.table_id, c.get_table(t).num_rows) for d in ('stylehub_bronze','stylehub_silver','stylehub_gold') for t in c.list_tables(d)]"
```

Each step is also saved in `stylehub_ops.pipeline_runs`.

## Step 8. Run it with Airflow (optional)

See [deploy/airflow/README.md](../../deploy/airflow/README.md). In short:

```powershell
# add the AIRFLOW_ values to secrets\.env (names are at the end of .env.example)
docker compose --env-file secrets/.env --profile airflow up -d --build
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow dags test stylehub_daily 2026-10-15
```

All four tasks should end as `success`. Open http://localhost:8080 (or your `AIRFLOW_WEB_PORT`) to see the DAG.

## Step 9. Prove the pipeline is safe to repeat

Run Step 6 again for the same date. Bronze replaces that day's batch, so its row counts stay the same, and the Silver row counts stay the same too.

## Step 9b. Check the safety features (not run yet on real BigQuery)

These features were written and unit-tested with fakes. None has run on a real project yet, so do each check once and note what you see. Run them from the project folder in PowerShell.

| # | What to prove | How | Expected |
|---|---|---|---|
| 1 | Bronze is not doubled | Run `uv run python -m orchestration.run_daily --date 2026-10-16 --from-step ingest --to-step bronze` **twice**. Then in the BigQuery console: `SELECT COUNT(*) AS n, COUNT(DISTINCT _batch_id) AS batches FROM stylehub_bronze.orders` | `batches` grows by one per **day**, not per run. `n` after the second run equals `n` after the first |
| 2 | `fact_events` is incremental | Run `--from-step silver --to-step silver` twice. In the console, open Job history (or query `region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`) and compare the bytes of the `fact_events` job | The first run (the table was a plain table before) may scan 13 GB. The second run scans a few hundred MB at most. `SELECT COUNT(*) FROM stylehub_silver.fact_events` stays 107.9 million |
| 3 | Late events are kept | Not testable with the static dataset. Read the comment at the top of `dbt/models/marts/core/fact_events.sql` | The window is `events_lookback_days` (3) |
| 4 | `pipeline_runs` has rows | `SELECT run_id, step, status, rows_loaded, duration_seconds, error FROM stylehub_ops.pipeline_runs ORDER BY started_at DESC LIMIT 20` | One row per step, `status` = `success`, `rows_loaded` filled only for `bronze` |
| 5 | A row is not lost when BigQuery fails | `$env:BQ_OPS = "no_such_dataset"` then `uv run python -c "from orchestration.runs import record_run, run_row; from datetime import UTC, datetime; n = datetime.now(UTC); print(record_run(run_row('t1','test','2026-10-16','success',n,n)))"` | Prints `False`, and the file `logs\pipeline_runs_pending.jsonl` appears. Then `Remove-Item Env:BQ_OPS` and run the same command again: it prints `True` and the file is gone. Two rows (`t1` twice) are now in `pipeline_runs`: delete them by hand |
| 6 | "Did not run" check | `uv run python -m orchestration.check_freshness --max-age-hours 1000` then `uv run python -m orchestration.check_freshness --max-age-hours 0.001; $LASTEXITCODE` | First: `OK: the last good run ended ...`. Second: the alert text, exit code `1` (a Discord message only if `ALERT_WEBHOOK_URL` is set) |
| 7 | One compose file | `docker compose --profile dev --profile pipeline --profile airflow config --quiet` then `docker compose up -d postgres` then `docker compose --profile dev down` | No error. Postgres starts without an `secrets/.env` file |
| 8 | Retry | `uv run pytest src/tests/common/test_retry.py -q` | All pass. A real network error is hard to force, so this is checked with fakes only |

If one of these fails, send me the exact message and I will fix it.

## Step 10. Clean up and save money

```powershell
docker compose --env-file secrets/.env --profile airflow down
```

- `stylehub_bronze.events_raw` is a 15 GB copy. You can delete it after `events_partitioned` exists. If you delete it and later rebuild `events_partitioned`, the copy runs again.
- Run `git status` before every commit. Check that `secrets/` and the CSV files are not listed.

## Known gaps

| Gap | Effect |
|---|---|
| The Postgres and API code has not run on real sources. | `run_daily` does not call it. |
| Gold numbers were not checked by hand against the CSV files. | The tests only prove the layers agree with each other. |
| Service accounts per job are designed but not created. | One key does everything. The roles are in [DEPLOY_VM.md](DEPLOY_VM.md). |
| The VM and CD files have not run on real GCP. | Expect small fixes. |

## Where to look when something breaks

| Symptom | Look at |
|---|---|
| `KeyError` for a setting | `secrets\.env` and [README.md](../../README.md#configuration) |
| `DefaultCredentialsError` in a `python -c` command | Set `$env:GOOGLE_APPLICATION_CREDENTIALS` in that window |
| `Dataset ... was not found in location ...` | Region mismatch. Run `uv run python -m storage.events_bronze` |
| `Cannot add fields` when loading Bronze | An old Bronze table has other columns. Delete it if it holds nothing you need |
| `SchemaError` in ingest | The source columns changed. Read the message and fix `EXPECTED_SCHEMAS` |
| A step failed | The log line `step <name> FAILED`, then the `error` column in `pipeline_runs` |
