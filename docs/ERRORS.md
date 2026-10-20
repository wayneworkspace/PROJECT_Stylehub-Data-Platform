# Common Errors and Fixes

Each row: the message you see, why it happens, and the fix. Commands run from the project folder.

## Pipeline steps

| Error message | Cause | Fix |
|---|---|---|
| `events_partitioned is missing in Bronze` | The one-time events build never ran | `uv run python -m src.3_storage.events_bronze` |
| `bronze <table>: no Raw file for <date>` | Ingest did not write that day | Rerun `ingest` for the date, then `bronze` |
| `RowCountMismatch: Raw file has X rows but Bronze got Y` | Load job lost or added rows | Check `_stg_<table>` in Bronze, rerun `bronze`; partition is untouched |
| `SourceRowMismatch: read X rows, the source has Y` | Source changed during the read | Rerun the task; Postgres reads use `REPEATABLE READ` |
| `SchemaError: missing columns` / `type changes` | Course source table changed its columns | Update `_stylehub__sources.yaml` and the staging models |
| `SchemaError: pg_<table>: the source table changed` | A Postgres column was removed or changed type | Update `_stylehub_pg__sources.yaml` and the `stg_pg__` models; new columns only warn |
| `POSTGRES_URL is not set in secrets/.env` | Postgres URL missing | Add `POSTGRES_URL` to `secrets/.env` (see `.env.example`) |
| `password authentication failed` (Postgres) | Wrong or rotated password | Fix `POSTGRES_URL`; it is not retried on purpose |
| `DbtError: dbt build (<layer>) failed: model.x: error` | A dbt model or test failed | Read `logs/dbt/<layer>/dbt.log` (JSON) for the failing node |
| `dbt build ... failed: Database Error` | No BigQuery access for dbt | Check `GOOGLE_APPLICATION_CREDENTIALS` and dataset roles |
| `Ordering by expressions of type STRUCT is not allowed` | A CTE has the same name as a column, so BigQuery orders by the whole row | Rename the CTE (see `pg_monthly_top_customers.sql`) |
| `Not found: Job ...` on several models at once | `--fail-fast` cancelled parallel jobs after one model failed | Find the first `ERROR in model` line; that model is the real cause |
| Silver step fails on `pg_gold_matches_silver` because Gold tables are missing | Eager test selection pulls tests with one selected parent | Keep `--indirect-selection cautious` in `src/4_transform/run_dbt.py` |
| `Not found: Table ...pg_deleted_ids` in `pg_silver` | The reconcile step never ran | Run `pg_reconcile` once (it creates the table), then `pg_silver` |
| `pg_published_revenue_drift` WARN | Rows arrived or changed for a month that was already published | Expected; the published number stays. Check the late rows if the gap is large |
| `pg_products_history_is_continuous` fails | Two Bronze rows of a product share `updated_at` but differ | Look at that product in `stylehub_bronze.pg_products`; the history keeps the newest `_ingested_at` |
| `DefaultCredentialsError: Your default credentials were not found` | No GCP login in the container | Put the key in `secrets/`, set the relative path in `secrets/.env` |
| `Could not record the run in BigQuery` (warning) | `pipeline_runs` missing or no access | `terraform apply` creates it; grant `ops` dataEditor |

## Airflow and Docker

| Error message | Cause | Fix |
|---|---|---|
| `airflow-init didn't complete successfully` + `No module named 'config'` | Logging config path not on `sys.path` | Keep `PYTHONPATH: /opt/airflow` in `docker-compose.yaml` |
| `ModuleNotFoundError: No module named 'colorlog'` in a task | The image is older than `uv.lock` | Rebuild the image: `docker compose --env-file secrets/.env --profile airflow build` |
| `No module named 'pendulum'` before each task | Pipeline venv has no pendulum; harmless | Ignore; the task still runs |
| `set AIRFLOW_..._PASSWORD in secrets/.env` | An Airflow secret is empty | Fill the four `AIRFLOW_` values from `.env.example` |
| `ports are not available` | Port 8080 or 8501 already used | Set `AIRFLOW_WEB_PORT=8081` in `secrets/.env` |
| Task log shows old code after a change | Code is copied into the image | `docker compose ... up -d --build`, then clear the run |
| Backfill runs break each other | Parallel runs share `_stg_<table>` | Always pass `--max-active-runs 1` to `airflow backfill create` |
| `exec: "C:/Program Files/Git/opt/...": no such file` | Git Bash rewrites Linux paths | Prefix the command with `MSYS_NO_PATHCONV=1` |
| `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine` | Docker Desktop is not running | Start Docker Desktop and wait until `docker info` answers |
| ANSI codes such as `[31m` inside Airflow task logs | dbt colors its output and Airflow saves it to files | Keep `DBT_USE_COLORS: "false"` in `docker-compose.yaml` |
| REST API 404 for a run id | `+` and `:` in the run id not URL-encoded | Encode the id (`urllib.parse.quote(run_id, safe="")`) |

## dbt, tests and CI

| Error message | Cause | Fix |
|---|---|---|
| `dbt found 1 package(s) specified in packages.yml, but only 0 package(s) installed` | `dbt deps` was not run | `uv run dbt deps --project-dir dbt_project --profiles-dir dbt_project` (the image and CI run it) |
| `relationships_pg_dim_users_country__country__ref_country_regions_` WARN | A new country appeared | Add it to `dbt_project/seeds/country_regions.csv` |
| `log-path config in dbt_project.yml has been deprecated` | dbt 1.12 wants a CLI flag | Pass `--log-path logs/dbt`; never set it in the YAML |
| `Required test coverage of 100.0% not reached` | New code without a test | Add a test with the fakes in `tests/test_stages.py` |
| Coverage misses files that were never imported | Namespace packages (no `__init__.py`) | Keep `include_namespace_packages = true` in `pyproject.toml` |
| `TypeError: DagBag.__init__() got an unexpected keyword argument 'include_examples'` | Airflow 3 removed the argument | Call `DagBag(dag_folder)` only |
| `No module named 'utils_dag'` in the DAG test | Plain DagBag does not add the DAG folder | Insert `settings.DAGS_FOLDER` into `sys.path` first |
| Ruff `E402` after `import_module` aliases | Import placed below an alias line | Load the logger with `import_module("src.0_utils.logger")` like the stages |
| Ruff `DTZ001` in a test | Naive `datetime(...)` | Use `datetime.fromisoformat(...)` for naive Postgres times |
| CD `dbt build`: `Got unexpected extra argument (n)` | A literal `\n` instead of a line break in the `run:` block | End the line with ` \` and continue on the next line; check with `bash -n` |
| sqlfluff `unknown tag 'snapshot'` | sqlfluff cannot parse dbt snapshots | Snapshots stay out of the lint paths |

## Terraform

| Error message | Cause | Fix |
|---|---|---|
| `Error 409: Already exists` on apply | Resource made before Terraform | Keep `imports.tf`; `terraform plan` shows "to import" |
| `Cloud Resource Manager API has not been used` | API is off in the project | First apply enables it; or `gcloud services enable cloudresourcemanager.googleapis.com` |
| `Error acquiring the state lock` | Another plan or apply is running | Wait; `terraform force-unlock <id>` only if it crashed |
| `Failed to get existing workspaces: bucket doesn't exist` | State bucket not created | `gcloud storage buckets create gs://<state-bucket> --location=asia-southeast1` |
| `api_products: read N rows (M ids), the API reports K` | A product was added while paging, so a page shifted | Rerun `api_ingest`; it writes a new batch |
| `401` from the API | Wrong or expired `STYLEHUB_API_KEY` | Remove the key from `.env` (a new one is asked) or set a new one |
| `STYLEHUB_API_URL is not set` | API branch on without its address | Set it in `secrets/.env` and the GitHub variable `STYLEHUB_API_URL` |
| Pipeline run does not start at 02:00 | GitHub disabled the schedule after 60 days without a commit | Actions > Pipeline > Enable workflow |
| `403 ... bigquery.readsessions.create` in a Pipeline run | IAM change not applied yet | Merge and let CD apply; `sa-pipeline` gets `roles/bigquery.readSessionUser` |
| CI plan step skipped | `WIF_PLAN_SERVICE_ACCOUNT` variable not set | Set the variables from `terraform output github_variables` |

## Products API

| Error message | Cause | Fix |
|---|---|---|
| `dags trigger` fails with a duplicate logical date | Unpausing already created that run | Use the scheduled run, or another logical date |

## Alerts

| Error message | Cause | Fix |
|---|---|---|
| `ALERT_WEBHOOK_URL is not set; alert not sent` | No webhook in `secrets/.env`, or Airflow started before it was added | Add it, then `docker compose ... --profile airflow up -d` |
| `Could not send the alert: HTTPError` | Webhook deleted or wrong (Discord answers 401/404) | Create a new webhook in Discord, update `ALERT_WEBHOOK_URL` |
| `freshness` task fails with `stale Bronze tables` | A table was not loaded in 26 hours | Check the failed load step of that table, rerun it, then clear `freshness` |
| No Discord message for a GCP alert | Cloud Monitoring cannot post Discord's format | Read incidents in Cloud Monitoring, or add channels via `alert_notification_channels` |

## Review tooling

| Error message | Cause | Fix |
|---|---|---|
| `401 Authentication failed` from `ai-gateway.vercel.sh/typesafe` | The key is a TypeSafe key, not a Vercel key | Call the default `https://api.typesafe.ai` (as `include/scripts/jev_review.py` does) |
| `KeyError: 'AI_GATEWAY_API_KEY'` | TypeSafe key missing | Add `AI_GATEWAY_API_KEY` to `secrets/.env` |
