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
    pytest.importorskip("google.cloud.bigquery")  # the project environment has it, Airflow does not
    from stylehub.orchestration import run_daily

    text = DAG_FILE.read_text(encoding="utf-8")
    match = re.search(r"STEP_NAMES = \[(.*?)\]", text)
    dag_steps = re.findall(r'"(\w+)"', match.group(1))
    assert dag_steps == [name for name, _ in run_daily.STEPS] == EXPECTED_STEPS


def test_every_task_gets_the_airflow_run_id():
    text = DAG_FILE.read_text(encoding="utf-8")
    assert '"run_id": "{{ run_id }}"' in text  # the Python tasks
    assert "--run-id '{{{{ run_id }}}}'" in text  # the dbt tasks
    assert "run_id=run_id" in text  # run_python_step hands it to run_steps


@pytest.fixture(scope="module")
def dag_bag():
    pytest.importorskip("airflow")
    from airflow.dag_processing.dagbag import DagBag  # Airflow 3 (Airflow 2: airflow.models)

    return DagBag(dag_folder=str(DAG_FILE.parent))


def test_dag_loads_without_errors(dag_bag):
    assert dag_bag.import_errors == {}
    assert "stylehub_daily" in dag_bag.dags


def test_a_run_at_02_00_loads_the_day_before(dag_bag):
    """Airflow 3 turns a plain cron string into a trigger timetable, where ds is the SAME day.

    The pipeline needs the data interval (14th 02:00 to 15th 02:00 runs on the 15th), so ds is
    the 14th. This test fails if someone writes schedule="0 2 * * *" again.
    """
    import pendulum
    from airflow.timetables.base import DataInterval, TimeRestriction

    timetable = dag_bag.dags["stylehub_daily"].timetable
    assert type(timetable).__name__ == "CronDataIntervalTimetable"
    last = DataInterval(
        pendulum.datetime(2026, 10, 13, 2, tz="UTC"), pendulum.datetime(2026, 10, 14, 2, tz="UTC")
    )
    nxt = timetable.next_dagrun_info(
        last_automated_data_interval=last,
        restriction=TimeRestriction(earliest=None, latest=None, catchup=False),
    )
    assert nxt.run_after == pendulum.datetime(2026, 10, 15, 2, tz="UTC")
    assert nxt.data_interval.start == pendulum.datetime(2026, 10, 14, 2, tz="UTC")


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
        assert task.op_kwargs["run_id"] == "{{ run_id }}"
        assert task.python.endswith("/bin/python")


def test_dbt_steps_run_one_step_with_the_logical_date(dag_bag):
    dag = dag_bag.dags["stylehub_daily"]
    for step in ("silver", "gold"):
        task = dag.get_task(step)
        assert task.task_type == "BashOperator"
        assert "--date {{ ds }}" in task.bash_command
        assert "--run-id '{{ run_id }}'" in task.bash_command
        assert f"--from-step {step} --to-step {step}" in task.bash_command


def test_start_and_end_do_no_work(dag_bag):
    dag = dag_bag.dags["stylehub_daily"]
    assert dag.get_task("start").task_type == "EmptyOperator"
    assert dag.get_task("end").task_type == "EmptyOperator"


def test_the_dag_sends_one_alert_and_the_tasks_send_none():
    text = DAG_FILE.read_text(encoding="utf-8")
    assert "alert=False" in text  # the Python tasks
    assert "--no-alert" in text  # the dbt tasks
    assert '"on_failure_callback": alert_on_failure' in text  # sent once, after the retries
    assert '"execution_timeout"' in text  # a stuck task cannot run for ever


def test_the_alert_callback_never_prints_the_webhook_url(monkeypatch, capsys):
    import importlib.util
    import sys
    from unittest.mock import MagicMock

    # Airflow is not installed here. The callback uses none of it, so stand-ins are enough.
    for name in (
        "airflow",
        "airflow.sdk",
        "airflow.timetables",
        "airflow.timetables.interval",
        "airflow.providers",
        "airflow.providers.standard",
        "airflow.providers.standard.operators",
        "airflow.providers.standard.operators.bash",
        "airflow.providers.standard.operators.empty",
        "airflow.providers.standard.operators.python",
    ):
        monkeypatch.setitem(sys.modules, name, MagicMock())
    spec = importlib.util.spec_from_file_location("stylehub_daily", DAG_FILE)
    dag_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dag_module)
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://discord.example/secret-token")

    def fail(request, timeout):
        raise OSError(f"cannot reach {request.full_url}")

    monkeypatch.setattr(dag_module.urllib.request, "urlopen", fail)
    context = {"task_instance": MagicMock(task_id="gold", try_number=2), "ds": "2026-10-01"}
    dag_module.alert_on_failure(context)
    assert "secret-token" not in capsys.readouterr().out
