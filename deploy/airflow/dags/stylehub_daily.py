"""Daily StyleHub pipeline: ingest -> bronze -> silver -> gold.

This file only says WHEN and IN WHAT ORDER. The real work stays in src and dbt/.
Three kinds of task. Airflow and the pipeline live in different Python environments, so the work
is split in two:

- start and end are EmptyOperator. They do no work. They mark where one run begins and ends,
  so a run is easy to see in the UI.

- ingest and bronze are Python code. They run with ExternalPythonOperator: Airflow calls the
  function run_python_step() inside the pipeline environment (/opt/venv/stylehub).
- silver and gold start dbt. They run with BashOperator, which starts the same command you can
  run by hand (run_daily calls dbt, saves the run in pipeline_runs):

    python -m stylehub.orchestration.run_daily --date 2026-10-01 --from-step silver --to-step silver
        [--run-id <the Airflow run id>]

Monitoring: every attempt is recorded in pipeline_runs. The Streamlit dashboard in
src/stylehub/serving shows it.

Backfill (old days, on purpose): airflow dags backfill stylehub_daily -s 2026-10-01 -e 2026-10-07

Settings (environment variables of the Airflow machine):
    STYLEHUB_HOME     project folder, where pyproject.toml lives (default /opt/stylehub)
    STYLEHUB_PYTHON   Python of the pipeline environment (default /opt/venv/stylehub/bin/python)
    STYLEHUB_RUN      command prefix that starts Python in the project environment, used by the
                      dbt tasks (default "uv run")
"""

import os
from datetime import UTC, datetime, timedelta

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
    from stylehub.common.logs import PIPELINE_FORMAT, setup_cli_logging
    from stylehub.orchestration import run_daily

    setup_cli_logging(PIPELINE_FORMAT)  # without this the INFO lines of the step are lost
    run_daily.run_steps(data_date, step, step, run_id=run_id)


def dbt_command(step: str) -> str:
    """The shell command of one dbt task. {{ ds }} is the day Airflow is processing."""
    # PYTHONPATH lets "python -m stylehub.orchestration.run_daily" find the code in src.
    return (
        f"cd {PROJECT_HOME} && PYTHONPATH={PROJECT_HOME}/src "
        f"{RUN_PREFIX} python -m stylehub.orchestration.run_daily "
        f"--date {{{{ ds }}}} --from-step {step} --to-step {step} --run-id '{{{{ run_id }}}}'"
    )


default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    # A stuck task must not hold the DAG for hours (max_active_runs=1 would block tomorrow too).
    "execution_timeout": timedelta(hours=2),
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
