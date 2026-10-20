"""Daily StyleHub DAG: when and in what order steps run."""

from datetime import UTC, datetime, timedelta

# Airflow 3 imports: the Task SDK and the standard provider.
from airflow.providers.standard.operators.python import ExternalPythonOperator
from airflow.sdk import DAG, chain
from airflow.timetables.interval import CronDataIntervalTimetable
from utils_dag import (
    PIPELINE_PYTHON,
    PROJECT_HOME,
    alert_on_failure,
    run_freshness_check,
    run_python_step,
)

# Two branches; names match STEPS in run_daily.py.
CSV_STEPS = ["ingest", "bronze", "silver", "gold"]
PG_STEPS = ["pg_ingest", "pg_bronze", "pg_reconcile", "pg_silver", "pg_gold"]
API_STEPS = ["api_ingest", "api_bronze", "api_silver"]
PG_ENABLED = True
# shortcut: API branch off, the course API moved and its new base URL is unknown
# (the old Supabase URL is gone, 2026-10-20); set STYLEHUB_API_URL, then set True here,
# API_STEPS in pipeline.yml and api_products in 02_data_freshness.sql.
API_ENABLED = False
BRANCHES = [CSV_STEPS] + [PG_STEPS] * PG_ENABLED + [API_STEPS] * API_ENABLED
STEPS = [step for branch in BRANCHES for step in branch]

default_args = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    # A normal step takes under 2 minutes; stop a stuck one early.
    "execution_timeout": timedelta(minutes=30),
    "on_failure_callback": alert_on_failure,  # Discord message after the last retry
}

with DAG(
    dag_id="stylehub_daily",
    description="StyleHub: ingest, load Bronze, build Silver and Gold with dbt",
    default_args=default_args,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    # 02:00 UTC daily; the data interval keeps ds as yesterday.
    schedule=CronDataIntervalTimetable("0 2 * * *", timezone="UTC"),
    # Production runs from .github/workflows/pipeline.yml at the same hour and on the
    # same tables, so locally trigger this DAG by hand and never unpause it.
    is_paused_upon_creation=True,
    catchup=False,  # old days are loaded on purpose with a backfill
    # Silver and Gold are rebuilt whole, so runs never overlap.
    max_active_runs=1,
    # A run takes about 4 minutes; a run still going after an hour fails and alerts.
    dagrun_timeout=timedelta(hours=1),
    on_failure_callback=alert_on_failure,
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
        for step in STEPS
    }

    for branch in BRANCHES:  # ingest >> bronze >> silver >> gold, and so on
        chain(*(tasks[step] for step in branch))

    # After every branch: alert when a Bronze table was not loaded today.
    freshness = ExternalPythonOperator(
        task_id="freshness",
        python=PIPELINE_PYTHON,
        python_callable=run_freshness_check,
        op_kwargs={"data_date": "{{ ds }}", "project_home": PROJECT_HOME, "run_id": "{{ run_id }}"},
        expect_airflow=False,
        expect_pendulum=False,
    )
    [tasks[branch[-1]] for branch in BRANCHES] >> freshness
