"""Daily StyleHub pipeline: ingest -> bronze -> silver -> gold.

This file only says WHEN and IN WHAT ORDER. The real work stays in src and dbt/.
Three kinds of task. Airflow and the pipeline live in different Python environments, so the work
is split in two:

- start and end are EmptyOperator. They do no work. They mark where one run begins and ends,
  so a run is easy to see in the UI.

- ingest and bronze are Python code. They run with ExternalPythonOperator: Airflow calls the
  function run_python_step() inside the pipeline environment (/opt/venv/stylehub).
- silver and gold start dbt. They run with BashOperator, which starts the same command you can
  run by hand (run_daily calls dbt, saves the run in pipeline_runs and sends the alert):

    python -m stylehub.orchestration.run_daily --date 2026-10-01 --from-step silver --to-step silver
        [--run-id <the Airflow run id>]

Alerts: run_daily is started with --no-alert, so a failed attempt is recorded in pipeline_runs but
sends no message. The DAG sends ONE message itself (alert_on_failure) when a task has failed for
good, after its retries. This also catches a task that was killed (out of memory, SIGKILL), where
run_daily never gets the chance to write or alert anything.

Settings (environment variables of the Airflow machine):
    STYLEHUB_HOME     project folder, where pyproject.toml lives (default /opt/stylehub)
    STYLEHUB_PYTHON   Python of the pipeline environment (default /opt/venv/stylehub/bin/python)
    STYLEHUB_RUN      command prefix that starts Python in the project environment, used by the
                      dbt tasks (default "uv run")
    ALERT_WEBHOOK_URL Discord webhook for alert_on_failure (a secret; empty = no alert)
"""

import json
import os
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

# Airflow 3: the DAG API moved to the Task SDK (airflow.sdk) and the operators to the "standard"
# provider (airflow.providers.standard). The Airflow 2 paths no longer exist.
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import ExternalPythonOperator
from airflow.sdk import DAG, chain
from airflow.timetables.interval import CronDataIntervalTimetable

PROJECT_HOME = os.environ.get("STYLEHUB_HOME", "/opt/stylehub")
PIPELINE_PYTHON = os.environ.get("STYLEHUB_PYTHON", "/opt/venv/stylehub/bin/python")
RUN_PREFIX = os.environ.get("STYLEHUB_RUN", "uv run")

# Same names as the steps in orchestration/run_daily.py.
STEP_NAMES = ["ingest", "bronze", "silver", "gold"]
PYTHON_STEPS = ["ingest", "bronze"]  # Python code: ExternalPythonOperator
DBT_STEPS = ["silver", "gold"]  # dbt: BashOperator


def run_python_step(data_date: str, step: str, project_home: str, run_id: str) -> None:
    """Run one step inside the pipeline environment.

    Airflow copies the source of this function to the other Python, so it must not use anything
    defined outside it. Imports go inside.
    """
    import sys

    sys.path.insert(0, f"{project_home}/src")
    from stylehub.orchestration import run_daily

    run_daily.setup_logging()  # without this the INFO lines of the step are lost
    # alert=False: the DAG sends the alert (alert_on_failure), so a retry sends no second message.
    run_daily.run_steps(data_date, step, step, run_id=run_id, alert=False)


def dbt_command(step: str) -> str:
    """The shell command of one dbt task. {{ ds }} is the day Airflow is processing."""
    # PYTHONPATH lets "python -m stylehub.orchestration.run_daily" find the code in src.
    return (
        f"cd {PROJECT_HOME} && PYTHONPATH={PROJECT_HOME}/src "
        f"{RUN_PREFIX} python -m stylehub.orchestration.run_daily "
        f"--date {{{{ ds }}}} --from-step {step} --to-step {step} --run-id '{{{{ run_id }}}}' "
        "--no-alert"
    )


def alert_on_failure(context: dict[str, Any]) -> None:
    """One Discord message when a task failed for good (all retries used). Never raises.

    It uses only the standard library: the Airflow environment has no pipeline packages.
    The webhook URL is a secret, so it is never printed.
    """
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return
    task = context["task_instance"]
    text = (
        "StyleHub pipeline FAILED (Airflow)\n"
        f"task: {task.task_id}\ndate: {context.get('ds')}\nrun: {context.get('run_id')}\n"
        f"tries: {task.try_number}\nerror: {context.get('exception')}"
    )[:1900]  # Discord rejects messages over 2000 characters
    if not url.startswith("https://"):  # urlopen would also open file: and custom schemes
        return
    request = urllib.request.Request(  # noqa: S310 - https only, checked above
        url,
        data=json.dumps({"content": text}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "stylehub-airflow"},
    )
    try:
        urllib.request.urlopen(request, timeout=10).close()  # noqa: S310 - https only
    except Exception as exc:  # an alert problem must not hide the real failure
        print(f"Could not send the alert ({type(exc).__name__})")


default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    # A stuck task must not hold the DAG for hours (max_active_runs=1 would block tomorrow too).
    "execution_timeout": timedelta(hours=2),
    # Runs once, after the last retry. This is the alert, also for a killed task.
    "on_failure_callback": alert_on_failure,
}

with DAG(
    dag_id="stylehub_daily",
    description="StyleHub: ingest, load Bronze, build Silver and Gold with dbt",
    default_args=default_args,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    # 02:00 every day. A run at 02:00 on the 15th has ds = the 14th: yesterday's data.
    # Airflow 3 turns a plain cron string into a trigger timetable, where ds would be the 15th.
    # CronDataIntervalTimetable keeps the data interval (14th 02:00 to 15th 02:00) of Airflow 2.
    schedule=CronDataIntervalTimetable("0 2 * * *", timezone="UTC"),
    # Old days are loaded on purpose with: airflow dags backfill (see deploy/airflow/README.md)
    catchup=False,
    # Silver and Gold are rebuilt as a whole, so two runs must never overlap.
    max_active_runs=1,
    tags=["stylehub"],
) as dag:
    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    tasks = []
    for step in STEP_NAMES:
        if step in PYTHON_STEPS:
            task = ExternalPythonOperator(
                task_id=step,
                python=PIPELINE_PYTHON,
                python_callable=run_python_step,
                op_kwargs={
                    "data_date": "{{ ds }}",
                    "step": step,
                    "project_home": PROJECT_HOME,
                    # One id for the 4 tasks of a DAG run, so pipeline_runs groups them.
                    "run_id": "{{ run_id }}",
                },
                # The pipeline environment has no Airflow and no pendulum.
                expect_airflow=False,
                expect_pendulum=False,
            )
        else:
            task = BashOperator(task_id=step, bash_command=dbt_command(step))
        tasks.append(task)

    # start >> ingest >> bronze >> silver >> gold >> end
    chain(start, *tasks, end)
