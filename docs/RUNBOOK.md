# Runbook

How to set up the StyleHub project once and run it every day. Commands are `bash` (Git Bash) from the project folder.

Error messages and fixes: `ERRORS.md`. Longer per-tool guides live only on the operator's machine (`docs/` is git-ignored except these three files).

## 1. Set up the project (once)

### 1.1 Tools

| Tool | Version | Check |
|---|---|---|
| Git, Git Bash | any | `git --version` |
| uv | 0.12 or newer | `uv --version` |
| Python | 3.13 (uv installs it) | `uv run python --version` |
| Docker Desktop | with Compose v2 | `docker compose version` |
| Google Cloud CLI | any | `gcloud --version` |
| Terraform | 1.16.5 | `terraform version` |
| GitHub CLI | any, logged in | `gh auth status` |

### 1.2 Code and settings

```bash
git clone https://github.com/wayneworkspace/PROJECT_Stylehub-Data-Platform.git
cd PROJECT_Stylehub-Data-Platform
uv sync --extra dev --extra dbt --extra serving
mkdir -p secrets && cp .env.example secrets/.env      # fill in every value; secrets/ is never committed
```

Fill in `secrets/.env`:

| Value | What to put |
|---|---|
| `GCP_PROJECT_ID`, `GCS_BUCKET` | `dehehe-510014`, `end-to-end-pipeline` |
| `GOOGLE_APPLICATION_CREDENTIALS` | `secrets/<key>.json`: key of the pipeline service account, for Docker |
| `POSTGRES_URL` | The read-only course database URL |
| `AIRFLOW_DB_PASSWORD`, `AIRFLOW_ADMIN_PASSWORD` | New random passwords |
| `AIRFLOW_SECRET_KEY`, `AIRFLOW_FERNET_KEY` | Generate with the commands in `.env.example` |
| `AIRFLOW_WEB_PORT` | A free local port, for example `8082` |
| `ALERT_WEBHOOK_URL` | Discord webhook for alerts (Server settings → Integrations → Webhooks) |
| `AI_GATEWAY_API_KEY` | TypeSafe key, only for reviews |

### 1.3 Cloud resources (project Owner, once)

```bash
gcloud auth login && gcloud auth application-default login
gcloud config set project dehehe-510014
gcloud storage buckets create gs://dehehe-510014-tfstate --location=asia-southeast1 --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://dehehe-510014-tfstate --versioning
gcloud services enable cloudresourcemanager.googleapis.com
cp infra/terraform/terraform.tfvars.example infra/terraform/terraform.tfvars   # fill in; keep bucket_location and source_location

unset GOOGLE_APPLICATION_CREDENTIALS
TF_STATE_BUCKET=dehehe-510014-tfstate infra/scripts/deploy.sh plan    # expect 0 to destroy
terraform -chdir=infra/terraform apply tfplan
```

Then set the GitHub variables that the workflows read:

```bash
terraform -chdir=infra/terraform output -json github_variables | uv run python -c "
import json, subprocess, sys
for k, v in json.load(sys.stdin).items(): subprocess.run(['gh', 'variable', 'set', k, '--body', v], check=True)"
gh variable set GCS_BUCKET_LOCATION --body ASIA
gh variable set BQ_SOURCE_LOCATION --body US
```

For resources made before Terraform, add `import` blocks for the first apply and delete them afterwards.

### 1.4 One-time data loads

```bash
uv run python -m src.1_source.load_csv          # course CSVs in data/raw_data -> BigQuery source
uv run python -m src.3_storage.events_bronze    # build events_partitioned (scans about 15 GB, once)
uv run dotenv -f secrets/.env run -- dbt build --project-dir dbt_project --profiles-dir dbt_project --log-path logs/dbt --select tag:events   # fact_events, once
```

### 1.5 Start the services

```bash
docker compose --env-file secrets/.env --profile airflow up -d --build
docker compose --env-file secrets/.env --profile serving up -d --build
docker compose --env-file secrets/.env --profile airflow --profile serving ps    # all healthy or running
```

| Page | Address | Login |
|---|---|---|
| Airflow | `http://localhost:<AIRFLOW_WEB_PORT>` | `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` |
| Dashboard | `http://localhost:8501` | none (localhost only) |

Unpause `stylehub_daily` and `stylehub_api` in the Airflow UI (or `MSYS_NO_PATHCONV=1 docker compose --env-file secrets/.env --profile airflow exec -T airflow-scheduler airflow dags unpause stylehub_daily`).

## 2. Daily operation

The DAG runs by itself at 02:00 UTC (09:00 Vietnam time) and loads yesterday's data.

### 2.1 Morning check (5 minutes)

| Step | Where | Healthy |
|---|---|---|
| 1. Docker is running | `docker compose --env-file secrets/.env --profile airflow --profile serving ps` | All services up |
| 2. Last night's runs | Discord alert channel, then Airflow UI, Grid views of `stylehub_daily` and `stylehub_api` | No red alert; 9 green tasks, and the API run green with `no_new_rows` skipped |
| 3. Step history | Dashboard "Pipeline health", or `SELECT step, status, rows_loaded, error FROM stylehub_ops.pipeline_runs ORDER BY started_at DESC LIMIT 20` | `success` for each step today |
| 4. Data freshness | Dashboard "Data freshness" | No table older than 26 hours |
| 5. dbt warnings | `grep -h '"Done. PASS' logs/dbt/*/dbt.log \| tail -4` | `ERROR=0`; only the known item-order WARN |

The laptop must be on and Docker running at 02:00 UTC. The DAG has `catchup=False`: after a break Airflow runs only the newest missed day, so backfill the others (section 2.3).

### 2.2 When a task failed

1. The Discord alert names the task, run and first error line. Open the failed task log in the Airflow UI, or `logs/airflow/dag_id=stylehub_daily/run_id=<run>/task_id=<task>/attempt=<n>.log`.
2. Find the message in `ERRORS.md` and apply the fix.
3. If you changed code: `docker compose --env-file secrets/.env --profile airflow up -d --build`.
4. Clear the failed task with **Clear** in the UI (Grid view, click the task); tasks after it run again. The CLI `airflow tasks clear` does not match runs of this DAG on Airflow 3.3.2.

Every step is safe to rerun: Raw is append-only, Bronze replaces its day partition, dbt rebuilds tables.

### 2.3 Run or rerun past days

```bash
export MSYS_NO_PATHCONV=1
AF="docker compose --env-file secrets/.env --profile airflow exec -T airflow-scheduler airflow"
$AF dags trigger stylehub_daily -l 2026-10-16T02:00:00+00:00          # one data day
$AF backfill create --dag-id stylehub_daily --from-date 2026-10-10 --to-date 2026-10-16 --max-active-runs 1
```

### 2.4 Change code

```bash
git switch main && git pull
git switch -c feature/<short-name>                  # or fix/<short-name>
# edit, then run the checks:
uv run ruff check . && uv run ruff format --check .
uv run pytest                                       # must stay at 100% coverage
uv run sqlfluff lint dbt_project/models dbt_project/macros dbt_project/tests include/sql
terraform -chdir=infra/terraform fmt -check && terraform -chdir=infra/terraform validate
uvx pre-commit run --all-files
git push -u origin HEAD && gh pr create
```

After review and a green `ci_test.yml`, merge. `cd_deploy.yml` then applies Terraform, pushes the Airflow image and runs `dbt build` on production. Rebuild local Docker to pick up the change.

### 2.5 Stop and start

```bash
docker compose --env-file secrets/.env --profile airflow --profile serving down     # keeps run history
docker compose --env-file secrets/.env --profile airflow --profile serving up -d
```

## 3. Regular tasks

| When | Task |
|---|---|
| Weekly | Check `logs/` size; old files can be deleted |
| Weekly | Read Dependabot pull requests; merge when CI is green |
| Before a release | Run the ponytail + Jev review; report in `output/DD-MM-YYYY.md` (`.claude/REVIEW_RULES.md`) |
| Every 90 days | Rotate the key in `secrets/` and the Airflow passwords |

## 4. Incidents

| Symptom | First action |
|---|---|
| Postgres password changed | Update `POSTGRES_URL` in `secrets/.env`, then restart Airflow |
| Key file leaked | Disable the key in IAM, create a new one, replace it in `secrets/` |
| Wrong numbers in Gold | Fix the model, rerun `silver`/`gold` (or `pg_silver`/`pg_gold`); Bronze keeps every load |
| Bad Raw file | Raw is append-only; the next run writes a new batch and Bronze reads the newest |
| Terraform plan wants to destroy | Stop; check `bucket_location = "ASIA"` and `source_location = "US"` in `terraform.tfvars` |
