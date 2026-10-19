"""Daily products API DAG, written with the TaskFlow API.

api_ready (HttpSensor) -> plan_pages (Connection, Variable, XCom)
-> fetch_page x N (dynamic task mapping, pool api_pool)
-> any_rows (branch) -> api_bronze -> api_silver, or no_new_rows
"""

from datetime import UTC, datetime, timedelta

from airflow.providers.http.hooks.http import HttpHook
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import ExternalPythonOperator
from airflow.sdk import Variable, dag, task
from airflow.timetables.interval import CronDataIntervalTimetable
from utils_dag import PIPELINE_PYTHON, PROJECT_HOME, alert_on_failure, run_python_step

API_CONN = "stylehub_api"  # set by AIRFLOW_CONN_STYLEHUB_API in docker-compose.yaml
PAGE_SIZE_VAR = "stylehub_api_page_size"  # set by AIRFLOW_VAR_STYLEHUB_API_PAGE_SIZE


@dag(
    dag_id="stylehub_api",
    description="StyleHub: products API to Raw, Bronze and Silver",
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    # 02:30 UTC daily, after the main DAG started; ds stays yesterday.
    schedule=CronDataIntervalTimetable("30 2 * * *", timezone="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    on_failure_callback=alert_on_failure,
    default_args={
        "owner": "data-engineering",
        "retries": 2,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=15),
        "on_failure_callback": alert_on_failure,
    },
    tags=["stylehub", "api"],
)
def stylehub_api() -> None:
    # Waits without holding a worker slot (reschedule) until the API answers.
    api_ready = HttpSensor(
        task_id="api_ready",
        http_conn_id=API_CONN,
        endpoint="products",
        request_params={"limit": 1, "select": "id"},
        mode="reschedule",
        poke_interval=60,
        timeout=600,
    )

    @task
    def plan_pages() -> list[dict]:
        """One dict per page, all sharing one batch_id; returned through XCom."""
        import sys
        from importlib import import_module

        sys.path.insert(0, PROJECT_HOME)
        size = int(Variable.get(PAGE_SIZE_VAR, default=50))
        hook = HttpHook(method="GET", http_conn_id=API_CONN)
        total = hook.run("products", data={"limit": 1, "select": "id"}).json()["total"]
        batch_id = import_module("src.1_source.utils").new_id()  # stdlib only
        return [
            {"base_url": hook.base_url, "skip": skip, "limit": size, "batch_id": batch_id}
            for skip in range(0, total, size)
        ]

    @task.external_python(
        python=PIPELINE_PYTHON, pool="api_pool", expect_airflow=False, expect_pendulum=False
    )
    def fetch_page(page: dict, data_date: str, project_home: str) -> int:
        """One mapped task per page; the pool caps parallel requests."""
        import sys
        from importlib import import_module

        sys.path.insert(0, project_home)
        return import_module("src.2_ingestion.api_products").ingest_page(page, data_date)

    @task.branch
    def any_rows(counts: list[int]) -> str:
        """Skip Bronze and Silver when the API returned nothing."""
        return "api_bronze" if sum(counts) else "no_new_rows"

    def step(task_id: str) -> ExternalPythonOperator:
        return ExternalPythonOperator(
            task_id=task_id,
            python=PIPELINE_PYTHON,
            python_callable=run_python_step,
            op_kwargs={
                "data_date": "{{ ds }}",
                "step": task_id,
                "project_home": PROJECT_HOME,
                "run_id": "{{ run_id }}",
            },
            expect_airflow=False,
            expect_pendulum=False,
        )

    pages = plan_pages()
    counts = fetch_page.partial(data_date="{{ ds }}", project_home=PROJECT_HOME).expand(page=pages)
    api_bronze, api_silver = step("api_bronze"), step("api_silver")
    api_ready >> pages
    any_rows(counts) >> [api_bronze, EmptyOperator(task_id="no_new_rows")]
    api_bronze >> api_silver


stylehub_api()
