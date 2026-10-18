# Airflow

Airflow decides **when** and **in what order** the pipeline runs. The work stays in `src/` and `dbt_project/`.

The DAG `stylehub_daily` (`dags/main_etl_dag.py`) runs two branches every day at 02:00 UTC:

```
ingest -> bronze -> silver -> gold      course tables, full load
pg_ingest -> pg_bronze -> pg_silver -> pg_gold   Postgres, incremental load
```

Each task is an `ExternalPythonOperator`. It calls `utils_dag.run_python_step`, which runs one step of `src/4_transform/run_daily.py` in the pipeline environment (`/opt/venv/stylehub`) and records it in `pipeline_runs`. The silver and gold steps start dbt, each branch with its own dbt target folder.

The schedule is a `CronDataIntervalTimetable`, so `ds` is yesterday: the run at 02:00 on the 15th loads the 14th. A plain cron string in Airflow 3 would load one day too late.

## Run Airflow with Docker Compose

You need Docker Desktop (WSL 2 on Windows). Add the `AIRFLOW_` values from `.env.example` to `secrets\.env` and fill in the four empty ones: two passwords, the secret key and the Fernet key. Then, from the project folder:

```powershell
docker compose --env-file secrets/.env --profile airflow up -d --build
```

Open <http://localhost:8080> and log in with `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD`. If port 8080 is taken, set `AIRFLOW_WEB_PORT=8081`. Turn on the DAG `stylehub_daily`.

```powershell
docker compose --env-file secrets/.env --profile airflow ps                                # what is running
docker compose --env-file secrets/.env --profile airflow logs -f airflow-scheduler
docker compose --env-file secrets/.env --profile airflow logs -f airflow-dag-processor   # DAG import errors
docker compose --env-file secrets/.env --profile airflow down                              # stop, keep the data
docker compose --env-file secrets/.env --profile airflow down -v                           # stop, delete the data
```

| File | Purpose |
|---|---|
| `dags/main_etl_dag.py` | The DAG |
| `dags/utils_dag.py` | Where the pipeline lives and how a task runs a step |
| `../docker-compose.yaml` | The `airflow` profile: Postgres, a one-time init, the API server, the DAG processor, the scheduler |
| `../Dockerfile` | Airflow plus a second Python environment with `requirements.txt` (pipeline and dbt) |

Code and DAGs are copied into the image, so rebuild (`up -d --build`) after a change. Only `secrets/` is mounted, read-only, and the key file named in `secrets/.env` must be inside it.

## Run one day by hand

```powershell
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow dags test stylehub_daily 2026-10-01
```

## Run old days (backfill)

```powershell
docker compose --env-file secrets/.env --profile airflow exec airflow-scheduler airflow backfill create --dag-id stylehub_daily --from-date 2026-09-25 --to-date 2026-10-01 --max-active-runs 1
```

Always add `--max-active-runs 1`: backfill ignores the DAG limit, and parallel runs share one Bronze staging table per source table. Every run is safe to repeat.

## Good to know

- Stop Airflow (`down`) when you do not use it; a VM costs money while it runs.
- The log line `No module named 'pendulum'` before each task is harmless; the tasks still pass.
- The login (Simple Auth Manager, one admin user) is for a local container only.
