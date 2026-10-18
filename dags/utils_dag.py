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
