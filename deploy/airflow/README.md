# Airflow

Airflow decides **when** and **in what order** the pipeline runs.
The real work stays in `src/python` and `dbt/`.

The DAG is `dags/stylehub_daily.py`. It has 4 steps in a line, between two empty marker tasks:

```
start -> ingest -> bronze -> silver -> gold -> end
```

Each task runs one step of the same code as `python -m orchestration.run_daily`, so every step can also be run by hand, without Airflow:

| Task | Operator | How it runs |
|---|---|---|
| `start`, `end` | `EmptyOperator` | Does no work. Marks where a run begins and ends |
| `ingest`, `bronze` | `ExternalPythonOperator` | Airflow calls a Python function inside the pipeline environment (`/opt/venv/stylehub`) |
| `silver`, `gold` | `BashOperator` | Starts `run_daily`, which starts dbt, saves the run and sends the alert |

## Run Airflow with Docker Compose

You need Docker Desktop running (it needs WSL 2 on Windows).

PowerShell, from the project folder:

```powershell
# Add the AIRFLOW_ values to secrets\.env. The names are at the end of .env.example.
# Fill in the three empty ones: the two passwords and the secret key.

docker compose --env-file secrets/.env --profile airflow up -d --build
```

The compose file is the one in the project folder (`docker-compose.yaml`). It also holds the sample
Postgres and the pipeline image. The `airflow` profile picks only the Airflow containers.

The first build takes a few minutes. Then open <http://localhost:8080> (or the port in
`AIRFLOW_WEB_PORT`) and log in with the user and password from `secrets\.env`.
If you see "ports are not available", another program uses port 8080. Set `AIRFLOW_WEB_PORT=8081`
in `secrets\.env` and run the `up` command again. Turn on the DAG `stylehub_daily`.

Useful commands:

```powershell
docker compose --env-file secrets/.env --profile airflow ps          # what is running
docker compose --env-file secrets/.env --profile airflow logs -f airflow-scheduler
docker compose --env-file secrets/.env --profile airflow down        # stop (keeps the data)
docker compose --env-file secrets/.env --profile airflow down -v     # stop and delete Airflow's data
```

What the files do:

| File | Purpose |
|---|---|
| `dags/stylehub_daily.py` | The DAG |
| `.env.example` | Names of the passwords. Copy it to `.env`. Git ignores `.env` |
| `../../docker-compose.yaml` | The `airflow` profile: 4 containers (a Postgres for Airflow's own data, a one-time setup, the web page, the scheduler) |
| `Dockerfile` | Airflow image plus a second Python environment (`/opt/venv/stylehub`) with the pipeline's packages and dbt |

How it works:
- Airflow and the pipeline need different package versions, so they use two Python environments.
- The project folder is mounted at `/opt/stylehub`, so a code change is used by the next task without a rebuild.
  Rebuild only when `pyproject.toml` or `uv.lock` changes.
- `secrets/` is mounted read-only. The key file named in `secrets/.env` must be inside `secrets/`.

## Run old days (backfill)

```powershell
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow dags backfill stylehub_daily -s 2026-09-25 -e 2026-10-01
```

This replaced `orchestration/backfill.py`. Every run is safe to repeat.

## Other way: without Docker (WSL 2 or Linux)

Airflow does not run on plain Windows. In WSL 2 or on a Linux VM:

```bash
uv venv ~/airflow-venv --python 3.12
uv pip install --python ~/airflow-venv/bin/python "apache-airflow==2.10.5" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.5/constraints-3.12.txt"

export AIRFLOW_HOME=~/airflow
export STYLEHUB_HOME=/opt/stylehub          # folder with pyproject.toml and secrets/.env
export AIRFLOW__CORE__DAGS_FOLDER=$STYLEHUB_HOME/deploy/airflow/dags
~/airflow-venv/bin/airflow standalone
```

Install the pipeline first in `STYLEHUB_HOME`: `uv sync --extra dbt`.

## Good to know

- `ds` is the day being processed. The run at 02:00 on the 15th loads the 14th.
- `retries` is 1. `run_step` already sends an alert on each failure, so more retries mean more alerts.
- The service account key stays in `secrets/` (git ignores it). Never put keys in the DAG file.
- Airflow runs all day. Stop it (`down`) when you are not using it. A VM costs money while it runs.
- Not verified: the Docker build and `up` (no Docker in the place where this was written), a real
  DAG run, BigQuery runs and the Discord alert.
  Verified: the DAG loads in Airflow 2.10.5, the compose file is valid, and the `uv sync` +
  `uv run --no-sync` way of starting the pipeline works on Linux.
