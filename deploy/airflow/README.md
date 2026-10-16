# Airflow

Airflow decides **when** and **in what order** the pipeline runs.
The real work stays in `src` and `dbt/`.

The DAG is `dags/stylehub_daily.py`. It has 4 steps in a line, between two empty marker tasks:

```
start -> ingest -> bronze -> silver -> gold -> end
```

Each task runs one step of the same code as `python -m stylehub.orchestration.run_daily`, so every step can also be run by hand, without Airflow:

| Task | Operator | How it runs |
|---|---|---|
| `start`, `end` | `EmptyOperator` | Does no work. Marks where a run begins and ends |
| `ingest`, `bronze` | `ExternalPythonOperator` | Airflow calls a Python function inside the pipeline environment (`/opt/venv/stylehub`) |
| `silver`, `gold` | `BashOperator` | Starts `run_daily`, which starts dbt and saves the run |

This is Airflow **3**. The DAG imports from `airflow.sdk` and `airflow.providers.standard`, and the schedule is a `CronDataIntervalTimetable`. A plain cron string would make `ds` the day of the run in Airflow 3, so every run would load one day too late.

## Run Airflow with Docker Compose

You need Docker Desktop running (it needs WSL 2 on Windows).

PowerShell, from the project folder:

```powershell
# Add the AIRFLOW_ values to secrets\.env. The names are at the end of .env.example.
# Fill in the three empty ones: the two passwords and the secret key.

docker compose --env-file secrets/.env --profile airflow up -d --build
```

The compose file is the one in the project folder (`docker-compose.yaml`). It also holds the pipeline
image. The `airflow` profile picks only the Airflow containers.

The first build takes a few minutes. Then open <http://localhost:8080> (or the port in
`AIRFLOW_WEB_PORT`) and log in with `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD` from `secrets\.env`.
If you see "ports are not available", another program uses port 8080. Set `AIRFLOW_WEB_PORT=8081`
in `secrets\.env` and run the `up` command again. Turn on the DAG `stylehub_daily`.

Useful commands:

```powershell
docker compose --env-file secrets/.env --profile airflow ps          # what is running
docker compose --env-file secrets/.env --profile airflow logs -f airflow-scheduler
docker compose --env-file secrets/.env --profile airflow logs -f airflow-dag-processor   # DAG import errors
docker compose --env-file secrets/.env --profile airflow down        # stop (keeps the data)
docker compose --env-file secrets/.env --profile airflow down -v     # stop and delete Airflow's data
```

What the files do:

| File | Purpose |
|---|---|
| `dags/stylehub_daily.py` | The DAG |
| `.env.example` | Names of the passwords. Copy it to `.env`. Git ignores `.env` |
| `../../docker-compose.yaml` | The `airflow` profile: 5 containers (a Postgres for Airflow's own data, a one-time setup, the API server with the web page, the DAG processor, the scheduler) |
| `Dockerfile` | Airflow image plus a second Python environment (`/opt/venv/stylehub`) with the pipeline's packages and dbt |

How it works:
- Airflow and the pipeline need different package versions, so they use two Python environments.
- The code (`src/stylehub` and `dbt`) and the DAG (`dags/`) are copied into the image. The whole project is **not** mounted,
  so Airflow cannot read your `.git` or other files. After a code change, rebuild: `... up -d --build`.
- Only `secrets/` is mounted, read-only. The key file named in `secrets/.env` must be inside `secrets/`.

## Run old days (backfill)

```powershell
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow backfill create --dag-id stylehub_daily --from-date 2026-09-25 --to-date 2026-10-01 --max-active-runs 1
```

Always add `--max-active-runs 1`. The DAG limit `max_active_runs=1` does not apply to a backfill, and runs at the same time
share one Bronze staging table per source table (`_stg_<table>`), so they break each other.

This replaced `orchestration/backfill.py`. Every run is safe to repeat.

## Other way: without Docker (WSL 2 or Linux)

Airflow does not run on plain Windows. In WSL 2 or on a Linux VM:

```bash
uv venv ~/airflow-venv --python 3.12
uv pip install --python ~/airflow-venv/bin/python "apache-airflow==3.3.2" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"

export AIRFLOW_HOME=~/airflow
export STYLEHUB_HOME=/opt/stylehub          # folder with pyproject.toml and secrets/.env
export AIRFLOW__CORE__DAGS_FOLDER=$STYLEHUB_HOME/deploy/airflow/dags
~/airflow-venv/bin/airflow standalone
```

Install the pipeline first in `STYLEHUB_HOME`: `uv sync --extra dbt`.

## Good to know

- `ds` is the day being processed. The run at 02:00 on the 15th loads the 14th.
- `retries` is 1. Each task has a 2 hour timeout.
- Monitoring: every attempt is saved in `pipeline_runs`; the Streamlit page (`--profile serving`) shows it.
- The service account key stays in `secrets/` (git ignores it). Never put keys in the DAG file.
- Airflow runs all day. Stop it (`down`) when you are not using it. A VM costs money while it runs.
- Verified (2026-10-16): the Docker image builds (about 21 minutes the first time), `up -d` starts the five containers (`airflow-init` exits with 0 and the API server turns healthy), and `airflow dags test stylehub_daily 2026-10-15` ran all six tasks to success on real GCS and BigQuery (Silver 50/50, Gold 38/38). In a real `apache-airflow==3.3.2` install the DAG also loads without errors, the task order, the operators and the timetable are right (the run of the 15th has `ds` = the 14th), and the DAG tests pass.
- Not verified: a run started by the scheduler itself at 02:00 UTC, the login with the Simple Auth Manager password file. The log shows `No module named 'pendulum'` before each Python task. The tasks still pass, so it looks harmless, but the cause is not checked. The base image is pinned by digest (`3.3.2-python3.12`, read on 2026-10-16).
- Airflow 3 login: one admin user from `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD` (the Simple
  Auth Manager). It is meant for a local container. For a shared server, use another auth manager.
