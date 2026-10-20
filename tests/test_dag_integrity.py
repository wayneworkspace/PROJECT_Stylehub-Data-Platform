"""DAGs load without import errors; runs inside the Airflow image."""

import sys
from importlib import import_module
from itertools import pairwise

import pytest

dagbag = pytest.importorskip("airflow.dag_processing.dagbag")
settings = pytest.importorskip("airflow.settings")


def test_dags_load() -> None:
    sys.path.insert(0, settings.DAGS_FOLDER)  # Airflow does this when it parses DAGs (utils_dag)
    bag = dagbag.DagBag(settings.DAGS_FOLDER)
    assert not bag.import_errors, bag.import_errors
    dag = bag.dags["stylehub_daily"]
    main_dag = import_module("main_etl_dag")  # PG_ENABLED pauses the Postgres branch
    csv = ["ingest", "bronze", "silver", "gold"]
    pg = ["pg_ingest", "pg_bronze", "pg_reconcile", "pg_silver", "pg_gold"]
    branches = [csv, pg] if main_dag.PG_ENABLED else [csv]
    assert set(dag.task_ids) == {*(t for b in branches for t in b), "freshness"}
    for branch in branches:
        for before, after in pairwise(branch):
            assert dag.get_task(after).upstream_task_ids == {before}
    assert dag.get_task("freshness").upstream_task_ids == {b[-1] for b in branches}
    assert dag.on_failure_callback and dag.default_args["on_failure_callback"]
