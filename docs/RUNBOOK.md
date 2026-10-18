# Runbook

How to set up, run, check and fix the StyleHub pipeline. Commands are PowerShell from the project folder unless marked `bash`.

## 1. First-time setup

```powershell
uv sync --extra dev --extra dbt --extra serving
copy .env.example secrets\.env        # fill in every value; never commit secrets/
gcloud auth application-default login # or a key file in secrets/ for Docker
```

Fill in `GCP_PROJECT_ID`, `GCS_BUCKET`, `POSTGRES_URL`, the four `AIRFLOW_` secrets and, for Docker, `GOOGLE_APPLICATION_CREDENTIALS=secrets/<key>.json`.

## 2. Infrastructure (Terraform)

One-time bootstrap by a project Owner:

```powershell
gcloud storage buckets create gs://<state-bucket> --location=asia-southeast1 --uniform-bucket-level-access
copy infra\terraform\terraform.tfvars.example infra\terraform\terraform.tfvars   # fill it in
```

Plan and apply (`bash`; the script saves plain logs to `logs/infra/`):

```bash
TF_STATE_BUCKET=<state-bucket> infra/scripts/deploy.sh plan    # review the plan
TF_STATE_BUCKET=<state-bucket> infra/scripts/deploy.sh apply   # asks before it changes anything
```

After the first apply, set the GitHub variables, then CD applies future changes:

```powershell
terraform -chdir=infra/terraform output -json github_variables
gh variable set WIF_PLAN_SERVICE_ACCOUNT --body <value>   # repeat for each key
gh variable set GCS_BUCKET_LOCATION --body ASIA
gh variable set BQ_SOURCE_LOCATION --body US
```

`imports.tf` adopts resources that existed before Terraform; delete it after the first apply, and before using a new project. The old accounts `sa-ingest`, `sa-transform`, `sa-monitor`, `sa-dbt-ci` and the `dbt_ci_*` datasets are no longer managed; delete them by hand once nothing uses them.

## 3. One-time data loads

```powershell
uv run python -m src.1_source.load_csv        # course CSVs in data/raw_data -> BigQuery source
uv run python -m src.3_storage.events_bronze  # build events_partitioned (about 15 GB scan, once)
```

## 4. Run Airflow

```powershell
docker compose --env-file secrets/.env --profile airflow up -d --build
docker compose --env-file secrets/.env --profile airflow ps
docker compose --env-file secrets/.env --profile airflow down       # stop, keep data
```

Open `http://localhost:<AIRFLOW_WEB_PORT>`. The DAG `stylehub_daily` runs at 02:00 UTC with two branches:
`ingest -> bronze -> silver -> gold` and `pg_ingest -> pg_bronze -> pg_silver -> pg_gold`.

Run one day by hand, rerun a failed run, or backfill:

```powershell
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow dags test stylehub_daily 2026-10-16
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow tasks clear stylehub_daily -s 2026-10-16 -e 2026-10-16 -y
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow backfill create --dag-id stylehub_daily --from-date 2026-10-10 --to-date 2026-10-16 --max-active-runs 1
```

## 5. Health checks

| Check | Command | Healthy result |
|---|---|---|
| Airflow API is up | `curl http://localhost:<port>/api/v2/version` | JSON with `"version":"3.3.2"` |
| DAG loads | `docker compose ... exec airflow-scheduler airflow dags list-import-errors` | `No data found` |
| Latest run state | Airflow UI, Grid view of `stylehub_daily` | Every task green |
| Step history | `SELECT step, status, rows_loaded, error FROM stylehub_ops.pipeline_runs ORDER BY started_at DESC LIMIT 20` | `success` rows for today |
| Bronze freshness | Dashboard, "Data freshness" | No warning older than 26 hours |
| Dashboard is up | `curl http://localhost:8501/_stcore/health` | `ok` |
| Pipeline venv packages | `MSYS_NO_PATHCONV=1 docker compose ... exec -T airflow-scheduler /opt/venv/stylehub/bin/python -c "import colorlog, sqlalchemy"` | No error |

## 6. Logs

| Component | Where | Format |
|---|---|---|
| Airflow tasks | `logs/airflow/dag_id=stylehub_daily/run_id=.../task_id=.../attempt=N.log` | JSON lines |
| Python code in `src/` | `logs/custom_scripts/unified-data_<env>_<module>_<date>.log` | Plain text, no colors |
| dbt | `logs/dbt/<layer>/dbt.log` | JSON |
| Terraform | `logs/infra/plan_<stamp>.log`, `apply_<stamp>.log` | Plain text |

## 7. Dashboard

```powershell
docker compose --env-file secrets/.env --profile serving up -d --build   # http://localhost:8501
uv run --extra serving streamlit run src/5_serving/dashboard.py           # without Docker
```

Pages: pipeline health and freshness, and the EDA page (quality, duplicates, outliers, KPIs over the last 90 days of Postgres order items).

## 8. Before a pull request

```powershell
uv run ruff check . ; uv run ruff format --check .
uv run pytest                           # fails below 100% coverage
uv run sqlfluff lint dbt_project/models dbt_project/macros dbt_project/tests include/sql
$env:GCP_PROJECT_ID="ci"; $env:GCS_BUCKET="ci"; uv run dbt parse --project-dir dbt_project --profiles-dir dbt_project --log-path logs/dbt
terraform -chdir=infra/terraform fmt -check ; terraform -chdir=infra/terraform validate
uvx pre-commit run --all-files
```

CI (`ci_test.yml`) runs the same checks on every pull request. CD (`cd_deploy.yml`) applies Terraform, pushes the tested Airflow image and runs dbt after a merge to `main`.

## 9. Incidents

| Symptom | First action |
|---|---|
| A task failed | Read its attempt log in `logs/airflow`, look the message up in `docs/ERRORS.md` |
| Postgres password changed | Update `POSTGRES_URL` in `secrets/.env`, restart Airflow |
| Key file leaked | Disable the key in IAM, create a new one, replace it in `secrets/` |
| Wrong data in Gold | Fix the model, then rerun `silver` and `gold`; Bronze keeps every load |
| Bad Raw file | Raw is append-only; the next run writes a new batch and Bronze reads the newest |
