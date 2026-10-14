"""Daily StyleHub pipeline: ingest -> bronze -> silver -> gold.

This file only says WHEN and IN WHAT ORDER. The real work stays in src/python and dbt/.
Three kinds of task. Airflow and the pipeline live in different Python environments, so the work
is split in two:

- start and end are EmptyOperator. They do no work. They mark where one run begins and ends,
  so a run is easy to see in the UI.

- ingest and bronze are Python code. They run with ExternalPythonOperator: Airflow calls the
  function run_python_step() inside the pipeline environment (/opt/venv/stylehub).
- silver and gold start dbt. They run with BashOperator, which starts the same command you can
  run by hand (run_daily calls dbt, saves the run in pipeline_runs and sends the alert):

    python -m orchestration.run_daily --date 2026-10-01 --from-step silver --to-step silver

Settings (environment variables of the Airflow machine):
    STYLEHUB_HOME     project folder, where pyproject.toml lives (default /opt/stylehub)
    STYLEHUB_PYTHON   Python of the pipeline environment (default /opt/venv/stylehub/bin/python)
    STYLEHUB_RUN      command prefix that starts Python in the project environment, used by the
                      dbt tasks (default "uv run")
"""

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import ExternalPythonOperator

PROJECT_HOME = os.environ.get("STYLEHUB_HOME", "/opt/stylehub")
PIPELINE_PYTHON = os.environ.get("STYLEHUB_PYTHON", "/opt/venv/stylehub/bin/python")
RUN_PREFIX = os.environ.get("STYLEHUB_RUN", "uv run")

# Same names as the steps in orchestration/run_daily.py.
STEP_NAMES = ["ingest", "bronze", "silver", "gold"]
PYTHON_STEPS = ["ingest", "bronze"]  # Python code: ExternalPythonOperator
DBT_STEPS = ["silver", "gold"]  # dbt: BashOperator


def run_python_step(data_date, step, project_home):
    """Run one step inside the pipeline environment.

    Airflow copies the source of this function to the other Python, so it must not use anything
    defined outside it. Imports go inside.
    """
    import sys

    sys.path.insert(0, f"{project_home}/src/python")
    from orchestration import run_daily

    run_daily.setup_logging()  # without this the INFO lines of the step are lost
    run_daily.run_steps(data_date, step, step)


def dbt_command(step: str) -> str:
    """The shell command of one dbt task. {{ ds }} is the day Airflow is processing."""
    # PYTHONPATH lets "python -m orchestration.run_daily" find the code in src/python.
    return (
        f"cd {PROJECT_HOME} && PYTHONPATH={PROJECT_HOME}/src/python "
        f"{RUN_PREFIX} python -m orchestration.run_daily "
        f"--date {{{{ ds }}}} --from-step {step} --to-step {step}"
    )


default_args = {
    "owner": "data-engineering",
    # run_step already alerts on every failure, so keep retries low to avoid duplicate alerts.
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="stylehub_daily",
    description="StyleHub: ingest, load Bronze, build Silver and Gold with dbt",
    default_args=default_args,
    start_date=datetime(2026, 10, 1),
    # 02:00 every day. A run at 02:00 on the 15th has ds = the 14th: yesterday's data.
    schedule="0 2 * * *",
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
                op_kwargs={"data_date": "{{ ds }}", "step": step, "project_home": PROJECT_HOME},
                # The pipeline environment has no Airflow and no pendulum.
                expect_airflow=False,
                expect_pendulum=False,
            )
        else:
            task = BashOperator(task_id=step, bash_command=dbt_command(step))
        tasks.append(task)

    # start >> ingest >> bronze >> silver >> gold >> end
    start >> tasks[0]
    for upstream, downstream in zip(tasks, tasks[1:]):
        upstream >> downstream
    tasks[-1] >> end
