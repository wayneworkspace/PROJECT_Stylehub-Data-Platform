"""Tests for deploy/airflow/dags/stylehub_daily.py.

Airflow and this project need different package versions, so they live in different
environments. That is why this file imports nothing from the project at the top:
  - the text test runs in the project environment (it reads the DAG file as text)
  - the DagBag tests run only where Airflow is installed (skipped otherwise)
"""

import re
from pathlib import Path

import pytest

DAG_FILE = Path(__file__).resolve().parents[3] / "deploy" / "airflow" / "dags" / "stylehub_daily.py"
EXPECTED_STEPS = ["ingest", "bronze", "silver", "gold"]


def test_dag_steps_are_the_pipeline_steps():
    pytest.importorskip("pandas")  # the project environment has it, the Airflow one does not
    from orchestration import run_daily

    text = DAG_FILE.read_text(encoding="utf-8")
    match = re.search(r"STEP_NAMES = \[(.*?)\]", text)
    dag_steps = re.findall(r'"(\w+)"', match.group(1))
    assert dag_steps == [name for name, _ in run_daily.STEPS] == EXPECTED_STEPS


@pytest.fixture(scope="module")
def dag_bag():
    pytest.importorskip("airflow")
    from airflow.models import DagBag

    return DagBag(dag_folder=str(DAG_FILE.parent), include_examples=False)


def test_dag_loads_without_errors(dag_bag):
    assert dag_bag.import_errors == {}
    assert "stylehub_daily" in dag_bag.dags


def test_tasks_run_in_pipeline_order(dag_bag):
    dag = dag_bag.dags["stylehub_daily"]
    assert [t.task_id for t in dag.topological_sort()] == ["start", *EXPECTED_STEPS, "end"]


def test_python_steps_call_the_function_in_the_pipeline_environment(dag_bag):
    dag = dag_bag.dags["stylehub_daily"]
    for step in ("ingest", "bronze"):
        task = dag.get_task(step)
        assert task.task_type == "ExternalPythonOperator"
        assert task.op_kwargs["data_date"] == "{{ ds }}"
        assert task.op_kwargs["step"] == step
        assert task.python.endswith("/bin/python")


def test_dbt_steps_run_one_step_with_the_logical_date(dag_bag):
    dag = dag_bag.dags["stylehub_daily"]
    for step in ("silver", "gold"):
        task = dag.get_task(step)
        assert task.task_type == "BashOperator"
        assert "--date {{ ds }}" in task.bash_command
        assert f"--from-step {step} --to-step {step}" in task.bash_command


def test_start_and_end_do_no_work(dag_bag):
    dag = dag_bag.dags["stylehub_daily"]
    assert dag.get_task("start").task_type == "EmptyOperator"
    assert dag.get_task("end").task_type == "EmptyOperator"
