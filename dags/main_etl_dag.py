"""Daily StyleHub DAG: when and in what order steps run."""

from datetime import UTC, datetime, timedelta

# Airflow 3 imports: the Task SDK and the standard provider.
from airflow.providers.standard.operators.python import ExternalPythonOperator
from airflow.sdk import DAG, chain
from airflow.timetables.interval import CronDataIntervalTimetable
from utils_dag import PIPELINE_PYTHON, PROJECT_HOME, run_python_step

# Two branches; names match STEPS in run_daily.py.
CSV_STEPS = ["ingest", "bronze", "silver", "gold"]
PG_STEPS = ["pg_ingest", "pg_bronze", "pg_silver", "pg_gold"]

default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    # Stop a stuck task so tomorrow's run is not blocked.
    "execution_timeout": timedelta(hours=2),
}

with DAG(
    dag_id="stylehub_daily",
    description="StyleHub: ingest, load Bronze, build Silver and Gold with dbt",
    default_args=default_args,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    # 02:00 UTC daily; the data interval keeps ds as yesterday.
    schedule=CronDataIntervalTimetable("0 2 * * *", timezone="UTC"),
    catchup=False,  # old days are loaded on purpose with a backfill
    # Silver and Gold are rebuilt whole, so runs never overlap.
    max_active_runs=1,
    tags=["stylehub"],
) as dag:
    tasks = {
        step: ExternalPythonOperator(
            task_id=step,
            python=PIPELINE_PYTHON,
            python_callable=run_python_step,
            op_kwargs={
                "data_date": "{{ ds }}",
                "step": step,
                "project_home": PROJECT_HOME,
                # One id for all tasks of a DAG run.
                "run_id": "{{ run_id }}",
            },
            # The pipeline environment has no Airflow and no pendulum.
            expect_airflow=False,
            expect_pendulum=False,
        )
        for step in CSV_STEPS + PG_STEPS
    }

    chain(*(tasks[step] for step in CSV_STEPS))  # ingest >> bronze >> silver >> gold
    chain(*(tasks[step] for step in PG_STEPS))  # pg_ingest >> ... >> pg_gold
