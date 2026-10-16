# Extending later

The repo is split so new tools can be added without rewriting. What stays fixed is the **contract**: dataset names (`stylehub_bronze`, `stylehub_silver`, `stylehub_gold`), table names and the grain of each table, and the Raw Zone paths.

## dbt (added, see `dbt/README.md`)

`dbt/` has 19 models in the dbt Labs layout (staging, intermediate, marts/core, marts/reporting), `sources` for Bronze, and the checks as tests.
Run it with `python -m stylehub.transform.run_dbt silver|gold`. `run_daily` calls it in the silver and gold steps.
`fact_events` is incremental (`insert_overwrite` by `event_date`). Not done yet: incremental for the other fact tables (they are small), and dbt for `bronze/01_events_partitioned.sql`.

## Airflow (added, see `deploy/airflow/README.md`)

`deploy/airflow/dags/stylehub_daily.py` runs ingest → bronze → silver → gold, one task per step.
`ingest` and `bronze` use `ExternalPythonOperator` (a Python function in the pipeline environment). `silver` and `gold` use `BashOperator` and call `run_daily --from-step X --to-step X`, which starts dbt. Logs, `pipeline_runs` and Discord alerts keep working in both.
Airflow is installed in its own environment, because its package versions clash with this project.
Use `airflow dags backfill` and the DAG schedule for past dates. The whole DAG has run on BigQuery with `airflow dags test`.

## Spark (for heavy processing, for example `events`)

1. Add `spark/`. Read Parquet from the Raw Zone (same `raw/stylehub/events/...` path) and write the result as a table in Silver or Gold.
2. Run on Dataproc. Keep the output table names unchanged so downstream layers are unaffected.
3. Move to Spark only when SQL on BigQuery stops being a good fit (complex processing, large scan cost). Record before and after measurements in `docs/design/DECISIONS.md`.

## Replacing Python ingestion with Airbyte

`src/stylehub/ingestion/` and Airbyte both write to the Raw Zone/Bronze. Switch the source of a table by disabling that table's ingest step in `run_daily.py`. If Airbyte loads Bronze directly, change `_ingested_at` to `_airbyte_extracted_at` in `dbt/models/silver/`.
