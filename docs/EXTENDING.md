# Extending later

The repo is split so new tools can be added without rewriting. What stays fixed is the **contract**: dataset names (`stylehub_bronze`, `stylehub_silver`, `stylehub_gold`), table names and the grain of each table, and the Raw Zone paths.

## dbt (replaces `src/sql/silver`, `src/sql/gold`, `src/sql/checks`)

1. Create a `dbt/` folder. Declare `sources` pointing at `stylehub_bronze`.
2. Each `src/sql/silver/NN_name.sql` becomes a model `models/silver/name.sql`: drop the `CREATE OR REPLACE TABLE` line, keep the `SELECT`, replace `` `${project}.${bronze}.x` `` with `{{ source('bronze', 'x') }}` and `` `${project}.${silver}.x` `` with `{{ ref('x') }}`. The `01_`, `02_` ordering is no longer needed because dbt derives order from `ref`.
3. Each file in `src/sql/checks/` becomes a test: grain checks become `unique` + `not_null`, the rest become singular tests (same shape: "return rows if broken").
4. Remove `make silver`, `make gold` and `make check` in favor of `dbt build`. `src/python/ingestion/` and `load_bronze` do not change.

## Airflow (replaces `src/python/pipeline/run_daily.py`)

1. `STEPS` in `run_daily.py` is already the list of steps: ingest → bronze → silver → gold → checks. Each step becomes a task.
2. Tasks call the existing CLIs (`python -m ingestion.incremental --date {{ ds }}`, `python -m pipeline.load_bronze --date {{ ds }}`, ...). No logic inside needs to change.
3. Retries and alerts are configured in Airflow, not written in Python code.
4. If dbt is already in use, the silver/gold/checks tasks merge into one `dbt build`.

## Spark (for heavy processing, for example `events`)

1. Add `spark/`. Read Parquet from the Raw Zone (same `raw/stylehub/events/...` path) and write the result as a table in Silver or Gold.
2. Run on Dataproc. Keep the output table names unchanged so downstream layers are unaffected.
3. Move to Spark only when SQL on BigQuery stops being a good fit (complex processing, large scan cost). Record before and after measurements in `docs/DECISIONS.md`.

## Replacing Python ingestion with Airbyte

`src/python/ingestion/` and Airbyte both write to the Raw Zone/Bronze. Switch the source of a table by disabling that table's ingest step in `run_daily.py`. If Airbyte loads Bronze directly, change `_ingested_at` to `_airbyte_extracted_at` in `src/sql/silver/`.
