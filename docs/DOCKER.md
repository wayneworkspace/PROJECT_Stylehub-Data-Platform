# Docker Commands

Start, stop, inspect and repair the local containers. Commands are `bash` (Git Bash) from the project folder.

```bash
export MSYS_NO_PATHCONV=1   # Git Bash: keep /opt/... paths as written
DC="docker compose --env-file secrets/.env"
```

## 1. Services

Nothing starts without a profile. Every value comes from `secrets/.env`.

| Profile | Service | Image | Port on this machine | Job |
|---|---|---|---|---|
| `airflow` | `airflow-db` | `postgres:16` | – | Airflow metadata; data in volume `airflow-db-data` |
| `airflow` | `airflow-init` | `Dockerfile` | – | Migrates the database, then exits |
| `airflow` | `airflow-apiserver` | `Dockerfile` | `127.0.0.1:<AIRFLOW_WEB_PORT>` | Web UI and REST API |
| `airflow` | `airflow-dag-processor` | `Dockerfile` | – | Parses `dags/` |
| `airflow` | `airflow-scheduler` | `Dockerfile` | – | Runs tasks (LocalExecutor) |
| `serving` | `dashboard` | `Dockerfile.dashboard` | `127.0.0.1:8501` | Streamlit, no login, so localhost only |

| Image | Base (pinned by digest) | Holds |
|---|---|---|
| `Dockerfile` | `apache/airflow:3.3.2-python3.13` | Airflow, plus the pipeline venv `/opt/venv/stylehub` from `requirements.txt`, and copies of `src/`, `include/`, `dbt_project/`, `dags/`, `config/` |
| `Dockerfile.dashboard` | `python:3.13-slim-bookworm` | `uv sync --extra serving`, `src/`, `include/`; runs as user `app` |

## 2. Mounts

| Host | Container | Mode |
|---|---|---|
| `secrets/` | `/opt/stylehub/secrets` (Airflow), `/app/secrets` (dashboard) | read only |
| `config/` | `/opt/airflow/config` | read only |
| `logs/airflow/` | `/opt/airflow/logs` | read and write |
| `logs/` | `/opt/stylehub/logs` | read and write |

## 3. Operate

```bash
$DC --profile airflow up -d --build         # start or update Airflow (rebuild after any code change)
$DC --profile serving up -d --build         # start or update the dashboard
$DC --profile airflow --profile serving ps  # status and health
$DC --profile airflow restart airflow-scheduler
$DC --profile airflow stop                  # pause, keep containers
$DC --profile airflow down                  # remove containers, keep the database volume
$DC --profile serving down
```

`down -v` also deletes the `airflow-db-data` volume and all run history. Use it only to reset Airflow on purpose.

## 4. Check

| Check | Command | Healthy result |
|---|---|---|
| Docker engine | `docker info --format '{{.ServerVersion}}'` | A version number |
| Containers | `$DC --profile airflow --profile serving ps` | `healthy` or `running`; `airflow-init` exited 0 |
| Airflow API | `curl -s http://localhost:<AIRFLOW_WEB_PORT>/api/v2/version` | JSON with `3.3.2` |
| Dashboard | `curl -s http://127.0.0.1:8501/_stcore/health` | `ok` |
| Port binding | `docker port endtoend-dashboard-1` | `8501/tcp -> 127.0.0.1:8501` |
| Compose file | `$DC --profile airflow --profile serving config --quiet` | No output |
| Image sizes | `docker images` | – |

## 5. Debug

```bash
$DC --profile airflow logs --tail 100 -f airflow-scheduler       # follow a service log
$DC --profile airflow logs airflow-init                          # why init failed
$DC --profile serving logs --tail 100 dashboard
$DC --profile airflow exec airflow-scheduler bash                # shell inside a container
$DC --profile airflow exec -T airflow-scheduler env | grep -E "^(GCP_|BQ_|GCS_|PYTHONPATH|DBT_)"   # settings the task sees
$DC --profile airflow exec -T airflow-scheduler ls /opt/stylehub/secrets                          # key file is mounted
docker stats --no-stream                                         # memory and CPU per container
```

Only `GCP_`, `BQ_`, `GCS_` and path values are safe to print. Never print `POSTGRES_URL` or any `AIRFLOW_*_PASSWORD`/`KEY` value.

## 6. Repair

| Problem | Fix |
|---|---|
| `failed to connect to the docker API` | Start Docker Desktop, wait until `docker info` answers |
| `ports are not available` | Change `AIRFLOW_WEB_PORT` in `secrets/.env`, then `up -d` |
| Old code runs | `$DC --profile airflow up -d --build`, then clear the task |
| Disk full | `docker system df`, then `docker image prune` (removes unused images only) |
| Init keeps failing | Read `$DC --profile airflow logs airflow-init`; check the four `AIRFLOW_` values in `secrets/.env` |
