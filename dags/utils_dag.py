"""DAG helpers: where the pipeline lives and how tasks run it."""

import os

PROJECT_HOME = os.environ.get("STYLEHUB_HOME", "/opt/stylehub")  # holds src/ and dbt_project/
# Python of the pipeline environment, separate from Airflow's own Python.
PIPELINE_PYTHON = os.environ.get("STYLEHUB_PYTHON", "/opt/venv/stylehub/bin/python")


def run_python_step(data_date: str, step: str, project_home: str, run_id: str) -> None:
    """Run one step in the pipeline environment; keep imports inside."""
    import sys
    from importlib import import_module

    sys.path.insert(0, project_home)
    run_daily = import_module("src.4_transform.run_daily")
    run_daily.run_step(data_date, step, run_id)


def run_freshness_check(data_date: str, project_home: str, run_id: str) -> None:
    """Last task: fail and alert when a Bronze table is stale."""
    import sys
    from importlib import import_module

    sys.path.insert(0, project_home)
    import_module("src.5_serving.freshness").check(data_date, run_id)


def alert_on_failure(context: dict) -> None:
    """Failure callback for tasks and DAG runs: one Discord message each."""
    import sys
    from importlib import import_module

    sys.path.insert(0, PROJECT_HOME)
    alerts = import_module("src.0_utils.alerts")
    ti, dag_run = context.get("ti"), context.get("dag_run")
    error = str(context.get("exception") or context.get("reason") or "see the log")
    alerts.send_alert(
        alerts.failure_message(
            dag_id=getattr(dag_run, "dag_id", "stylehub_daily"),
            task_id=getattr(ti, "task_id", None),
            run_id=getattr(dag_run, "run_id", "?"),
            error=error.splitlines()[0][:500] if error else "see the log",
            log_url=getattr(ti, "log_url", None),
        )
    )
