# Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `SchemaError: ... the source schema changed` | A column is missing or has another type. Read the message, then fix `EXPECTED_SCHEMAS` in `src/python/ingestion/schema_check.py` or the SQL. Use `--on-schema-change absorb` only on purpose. |
| `KeyError: 'GCP_PROJECT_ID'` (or `PG_HOST`) | `secrets/.env` is missing or incomplete. Copy `.env.example` to `secrets/.env` and fill it in. |
| `403` or "permission denied" | The service account lacks a role. Add the roles listed in the [prerequisites table](GETTING_STARTED.md#prerequisites). |
| `Not found: Dataset ...` | A dataset does not exist, or it is in another region than the query. Create the dataset, or check its location. |
| `Dataset ... was not found in location ...` | A query reads one region and writes to another. For `events`, run `python -m storage.events_bronze`. |
| `Provided Schema does not match Table ... Cannot add fields` | An old Bronze table has other columns. If it holds no data you need, delete it in BigQuery and run the bronze step again. |
| `DefaultCredentialsError` in a `python -c` command | Set `$env:GOOGLE_APPLICATION_CREDENTIALS` in that PowerShell window. `run_daily` reads it from `secrets/.env` itself. |
| `cannot import name 'storage' from 'google.cloud'` | The `.venv` is damaged, often by OneDrive. Run `uv sync --extra dev --extra dbt --reinstall`. |
| `load_bronze` says no files match | No Raw files exist for that table and date. Run the ingest step first. |
| "Unrecognized name" in a dbt model | The model used a wrong column name. Check the real columns in `INFORMATION_SCHEMA.COLUMNS` and edit the model. |
| `dbt` is not found | Run through `uv run`, or `uv sync --extra dbt` first. `run_dbt` looks for `dbt` on the PATH. |
| Bronze row count grows on a new day | Each day adds one full snapshot. This is by design. Re-running the same day does not add rows. |
| `pytest` says tests were "deselected" | Integration tests are off by default. Start the Docker Postgres and add `-m integration`. |
| `docker compose up` says port 5432 is in use | Another Postgres runs on your computer. Stop it, or change the port in `docker-compose.yaml`. |
| `docker compose up` starts nothing | Every service has a profile. Name the service (`up -d postgres`) or add `--profile airflow`. |
| `psql: connection to server on socket ... failed` right after `docker compose up` | Postgres is not ready yet. Run `docker compose up -d --wait postgres` so the command waits for the health check. |
| `airflow-init` stops with "set AIRFLOW_ADMIN_PASSWORD in secrets/.env" | You forgot `--env-file secrets/.env`, or an `AIRFLOW_` value in that file is empty. |
| A commit fails and files changed | A pre-commit hook fixed them, for example trailing spaces. Run `git add` again and commit again. |
| A commit is blocked by gitleaks | It found something that looks like a key. Remove the secret first. If it was a real key, rotate it. |
