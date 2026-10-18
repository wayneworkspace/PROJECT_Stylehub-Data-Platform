# Airflow Commands

Operate, check and debug the `stylehub_daily` DAG in local Docker. Commands are `bash` (Git Bash) from the project folder. Error fixes are in `ERRORS.md`.

```bash
# Short form used below; MSYS_NO_PATHCONV stops Git Bash rewriting /opt/... paths.
export MSYS_NO_PATHCONV=1
AF="docker compose --env-file secrets/.env --profile airflow exec -T airflow-scheduler airflow"
```

## 1. Access

| What | Value | Where it is set |
|---|---|---|
| Web UI | `http://localhost:<AIRFLOW_WEB_PORT>` (8082 on this machine) | `AIRFLOW_WEB_PORT` in `secrets/.env` |
| UI and API user | `AIRFLOW_ADMIN_USER` (default `admin`) | `secrets/.env` |
| UI and API password | `AIRFLOW_ADMIN_PASSWORD` | `secrets/.env` |
| Metadata database | Postgres `airflow-db`, database `airflow`, user `airflow`, password `AIRFLOW_DB_PASSWORD` | `secrets/.env`, `docker-compose.yaml` |
| Secret and Fernet keys | `AIRFLOW_SECRET_KEY`, `AIRFLOW_FERNET_KEY` | `secrets/.env` |

```bash
grep -E "^AIRFLOW_(ADMIN_USER|ADMIN_PASSWORD|WEB_PORT)=" secrets/.env   # show the login on screen only
```

Never paste these values into issues, logs or commits.

## 2. Paths

| What | Host | Container |
|---|---|---|
| DAG files | `dags/` (copied into the image) | `/opt/airflow/dags` |
| Pipeline code | `src/`, `include/`, `dbt_project/` (copied) | `/opt/stylehub/...` |
| Pipeline Python | – | `/opt/venv/stylehub/bin/python` |
| Logging config | `config/airflow_local_settings.py` | `/opt/airflow/config` |
| Task logs | `logs/airflow/dag_id=stylehub_daily/run_id=<run>/task_id=<task>/attempt=<n>.log` | `/opt/airflow/logs` |
| Script and dbt logs | `logs/custom_scripts/`, `logs/dbt/<layer>/` | `/opt/stylehub/logs` |
| GCP key and `.env` | `secrets/` (read-only mount) | `/opt/stylehub/secrets` |

Code is copied into the image: after a change run `docker compose --env-file secrets/.env --profile airflow up -d --build`.

## 3. DAG facts

| Item | Value |
|---|---|
| DAG id | `stylehub_daily` |
| Schedule | `0 2 * * *` UTC, one run per data day |
| Data date | `ds` = logical date = yesterday; run `scheduled__2026-10-17T02:00:00+00:00` loads 2026-10-16 |
| Tasks | `ingest -> bronze -> silver -> gold` and `pg_ingest -> pg_bronze -> pg_silver -> pg_gold` |
| Retries and limits | 1 retry after 5 minutes, 2-hour timeout per task, 1 active run |

## 4. Operate

```bash
$AF dags trigger stylehub_daily -l 2026-10-16T02:00:00+00:00   # run data day 2026-10-16
$AF dags pause stylehub_daily                                  # stop new runs
$AF dags unpause stylehub_daily
$AF backfill create --dag-id stylehub_daily --from-date 2026-10-10 --to-date 2026-10-16 --max-active-runs 1
$AF backfill create --dag-id stylehub_daily --from-date 2026-10-10 --to-date 2026-10-16 --max-active-runs 1 --reprocess-behavior failed
```

Always keep `--max-active-runs 1`: parallel runs share the `_stg_<table>` staging tables.

### Rerun a task (clear it)

In the UI: open the run in Grid view, click the task, then **Clear**. The CLI `airflow tasks clear` does not match runs of this DAG on 3.3.2, so use the UI or the REST API:

```bash
set -a; . <(grep -E "^AIRFLOW_(ADMIN_USER|ADMIN_PASSWORD|WEB_PORT)=" secrets/.env | sed 's/[[:space:]]*#.*$//'); set +a
B="http://localhost:${AIRFLOW_WEB_PORT:-8080}"
TOKEN=$(curl -s -X POST "$B/auth/token" -H "Content-Type: application/json" \
  -d "{\"username\":\"$AIRFLOW_ADMIN_USER\",\"password\":\"$AIRFLOW_ADMIN_PASSWORD\"}" | sed -E 's/.*"access_token":"([^"]+)".*/\1/')

# dry_run true only lists; set it to false to clear. only_failed false also clears successful tasks.
curl -s -X POST "$B/api/v2/dags/stylehub_daily/clearTaskInstances" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"dry_run": true, "only_failed": false, "dag_run_id": "scheduled__2026-10-17T02:00:00+00:00", "task_ids": ["pg_gold"]}'
```

## 5. Check

| Check | Command | Healthy result |
|---|---|---|
| Version | `$AF version` | `3.3.2` |
| DAG imports | `$AF dags list-import-errors` | `No data found` |
| Latest runs | `$AF dags list-runs stylehub_daily -o plain` | `success` |
| Task states of one run | `$AF tasks states-for-dag-run stylehub_daily 'scheduled__2026-10-17T02:00:00+00:00' -o plain` | Every task `success` |
| API alive | `curl -s http://localhost:<port>/api/v2/version` | JSON with the version |
| Latest run via API | `curl -s "$B/api/v2/dags/stylehub_daily/dagRuns?order_by=-run_after&limit=1" -H "Authorization: Bearer $TOKEN"` | `"state":"success"` |
| Containers | `docker compose --env-file secrets/.env --profile airflow ps` | `healthy` / `running` |

## 6. Debug

```bash
# Newest attempt log of one task, errors only
f=$(ls -t logs/airflow/dag_id=stylehub_daily/run_id=*/task_id=pg_gold/attempt=*.log | head -1); grep -E '"level":"error"|ERROR|Traceback' "$f" | tail -20

# Run one step inside the container, same code and venv as the task
docker compose --env-file secrets/.env --profile airflow exec -T -w /opt/stylehub airflow-scheduler \
  /opt/venv/stylehub/bin/python -c "from importlib import import_module; import_module('src.4_transform.run_daily').run_step('2026-10-16', 'pg_gold', 'manual-debug')"

# Pipeline venv has the packages
docker compose --env-file secrets/.env --profile airflow exec -T airflow-scheduler /opt/venv/stylehub/bin/python -c "import colorlog, sqlalchemy, dbt"

# Scheduler and API server logs
docker compose --env-file secrets/.env --profile airflow logs --tail 100 airflow-scheduler
docker compose --env-file secrets/.env --profile airflow logs --tail 100 airflow-apiserver

# Metadata database shell (read only queries, please)
docker compose --env-file secrets/.env --profile airflow exec airflow-db psql -U airflow -d airflow -c "SELECT run_id, state FROM dag_run ORDER BY run_after DESC LIMIT 5;"
```

The step working directory inside the container is `/opt/stylehub` (the DAG passes `project_home`). Every attempt is also written to BigQuery table `stylehub_ops.pipeline_runs`.
