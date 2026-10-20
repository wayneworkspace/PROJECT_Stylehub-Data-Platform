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
uv run dbt deps --project-dir dbt_project --profiles-dir dbt_project --log-path logs/dbt   # dbt_utils, from package-lock.yml
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

For a local run, unpause `stylehub_daily` in the Airflow UI (or `MSYS_NO_PATHCONV=1 docker compose --env-file secrets/.env --profile airflow exec -T airflow-scheduler airflow dags unpause stylehub_daily`).

## 2. Daily operation

GitHub Actions runs `.github/workflows/pipeline.yml` at 02:00 UTC (09:00 Vietnam time) and loads yesterday's data; no laptop needs to be on. `watchdog.yml` checks freshness again at 12:00 UTC. Airflow in local Docker runs the same steps for tests and demos.

### 2.1 Morning check (5 minutes)

| Step | Where | Healthy |
|---|---|---|
| 1. Last night's run | Discord alert channel, then GitHub > Actions > Pipeline | No red alert; the run is green |
| 2. Step history | Dashboard "Pipeline health", or `SELECT step, status, rows_loaded, error FROM stylehub_ops.pipeline_runs ORDER BY started_at DESC LIMIT 20` | `success` for each step today |
| 3. Data freshness | Dashboard "Data freshness" | No table older than 26 hours |
| 4. dbt warnings | Log of the Pipeline run, steps "silver" and "gold" | `ERROR=0`; only the known item-order WARN |

Open the Cloud Run dashboard with `gcloud run services proxy stylehub-dashboard --region asia-southeast1 --port 8501`, then `http://localhost:8501`. GitHub stops scheduled workflows after 60 days without a commit; re-enable them in the Actions tab.

### 2.2 When a run failed

1. The Discord alert links the failed run. Open it in GitHub Actions and read the first error.
2. Find the message in `ERRORS.md` and apply the fix (through a pull request if it is code).
3. Rerun: **Re-run failed jobs** on the run page, or start Pipeline by hand (section 2.3).

Every step is safe to rerun: Raw is append-only, Bronze replaces its day partition, dbt rebuilds tables.

### 2.3 Run or rerun past days

```bash
gh workflow run pipeline.yml -f data_date=2026-10-16          # one data day
for d in 2026-10-10 2026-10-11 2026-10-12; do gh workflow run pipeline.yml -f data_date=$d; done   # runs one after another
```

To publish a corrected month: `gh workflow run restate.yml -f months=2026-09-01 -f note="September returns"`, then approve the `production` environment on the run page.

With local Airflow instead: `docker compose --env-file secrets/.env --profile airflow exec -T airflow-scheduler airflow dags trigger stylehub_daily -l 2026-10-16T02:00:00+00:00` (set `MSYS_NO_PATHCONV=1` in Git Bash).

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

`main` is protected: a pull request merges only when the four CI checks pass. `cd_deploy.yml` then applies Terraform (prod and dev), pushes the tested dashboard image, runs `dbt build` on staging (`_dev` datasets), then on production, and puts the new dashboard on Cloud Run.

### 2.5 Local Docker

```bash
docker compose --env-file secrets/.env --profile airflow --profile serving down     # keeps run history
docker compose --env-file secrets/.env --profile airflow --profile serving up -d
```

### 2.6 Dev datasets

`infra/terraform/envs/dev` builds `stylehub_<layer>_dev` datasets from the same module as prod, with its own state (`stylehub-dev`). CD applies it and uses it as staging; tables there expire after 1 day. Point a dev `.env` at the `_dev` datasets (`terraform -chdir=infra/terraform/envs/dev output dataset_ids`) to try dbt changes without touching prod.

## 3. Regular tasks

| When | Task |
|---|---|
| Weekly | Check `logs/` size; old files can be deleted |
| Weekly | `uv run python include/scripts/dry_run_report.py`: bytes per query, to catch a missing partition filter |
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
