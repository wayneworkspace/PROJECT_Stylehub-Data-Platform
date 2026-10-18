"""DAGs load without import errors; runs inside the Airflow image."""

import sys
from itertools import pairwise

import pytest

dagbag = pytest.importorskip("airflow.dag_processing.dagbag")
settings = pytest.importorskip("airflow.settings")


def test_dags_load() -> None:
    sys.path.insert(0, settings.DAGS_FOLDER)  # Airflow does this when it parses DAGs (utils_dag)
    bag = dagbag.DagBag(settings.DAGS_FOLDER)
    assert not bag.import_errors, bag.import_errors
    dag = bag.dags["stylehub_daily"]
    csv = ["ingest", "bronze", "silver", "gold"]
    pg = ["pg_ingest", "pg_bronze", "pg_reconcile", "pg_silver", "pg_gold"]
    assert set(dag.task_ids) == {*csv, *pg, "freshness"}
    for branch in (csv, pg):
        for before, after in pairwise(branch):
            assert dag.get_task(after).upstream_task_ids == {before}
    assert dag.get_task("freshness").upstream_task_ids == {"gold", "pg_gold"}
    assert dag.on_failure_callback and dag.default_args["on_failure_callback"]

    api = bag.dags["stylehub_api"]
    flow = ["api_ready", "plan_pages", "fetch_page", "any_rows", "api_bronze", "api_silver"]
    assert set(api.task_ids) == {*flow, "no_new_rows"}
    assert api.get_task("fetch_page").pool == "api_pool"
    assert api.get_task("api_silver").upstream_task_ids == {"api_bronze"}
    assert api.get_task("any_rows").downstream_task_ids == {"api_bronze", "no_new_rows"}
