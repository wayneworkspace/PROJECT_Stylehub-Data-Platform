"""Pipeline stages against fake GCS, BigQuery, Postgres and dbt; no cloud needed."""

import ast
import io
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace as NS
from typing import ClassVar

import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml
from google.api_core import exceptions

config = import_module("src.1_source.config")
bq = import_module("src.1_source.bq")
retry = import_module("src.1_source.retry")
load_csv = import_module("src.1_source.load_csv")
csv_tables = import_module("src.2_ingestion.csv_tables")
pg_tables = import_module("src.2_ingestion.postgres_tables")
raw_writer = import_module("src.2_ingestion.raw_writer")
schema_check = import_module("src.2_ingestion.schema_check")
events_bronze = import_module("src.3_storage.events_bronze")
load_bronze = import_module("src.3_storage.load_bronze")
runs = import_module("src.3_storage.runs")
run_dbt = import_module("src.4_transform.run_dbt")
run_daily = import_module("src.4_transform.run_daily")


@pytest.fixture
def cfg() -> config.Settings:
    return config.Settings(
        GCP_PROJECT_ID="proj", GCS_BUCKET="bucket", POSTGRES_URL="postgresql+psycopg2://u:p@h/db"
    )


def job(value: object = None, rows: int = 0) -> NS:
    return NS(result=lambda: value, output_rows=rows)


class FakeBQ:
    """Records calls; tables maps table id to a table object."""

    def __init__(self, tables: dict | None = None, frame: pd.DataFrame | None = None) -> None:
        self.tables = tables or {}
        self.frame = frame
        self.calls: list[tuple] = []
        self.loaded_rows = 0
        self.query_rows: list[tuple] = []
        self.copy_fails_in: set[str] = set()

    def get_table(self, table_id: str) -> NS:
        if table_id not in self.tables:
            raise exceptions.NotFound(table_id)
        return self.tables[table_id]

    def get_dataset(self, dataset_id: str) -> NS:
        return NS(location="US")

    def list_rows(self, table: object, selected_fields: list) -> NS:
        self.calls.append(("list_rows", [f.name for f in selected_fields]))
        return NS(to_dataframe=lambda: self.frame)

    def query(self, sql: str, job_config: object = None) -> NS:
        self.calls.append(("query", sql))
        return (
            NS(
                result=lambda: None,
                to_dataframe=lambda: self.frame,
                __iter__=None,
            )
            if self.frame is not None
            else FakeRows(self.query_rows)
        )

    def copy_table(self, source: str, target: str, job_config: object, location: str) -> NS:
        self.calls.append(("copy", target, location))
        if location in self.copy_fails_in:
            raise exceptions.NotFound("no copy job here")
        return job()

    def load_table_from_uri(
        self, uri: str, target: str, job_config: object, location: str | None = None
    ) -> NS:
        self.calls.append(("load", uri))
        return job(rows=self.loaded_rows)

    def load_table_from_json(self, rows: list, table: str) -> NS:
        self.calls.append(("json", table, rows))
        return job()

    def create_table(self, table: object, exists_ok: bool) -> None:
        self.calls.append(("create", table.table_id, table.time_partitioning.expiration_ms))

    def delete_table(self, table_id: str, not_found_ok: bool) -> None:
        self.calls.append(("delete", table_id))


class FakeRows(list):
    def result(self) -> "FakeRows":  # like RowIterator: the rows themselves
        return self


class FakeBlob:
    def __init__(self, name: str, data: bytes = b"") -> None:
        self.name = name
        self.data = data

    def upload_from_string(self, data: bytes, content_type: str) -> None:
        self.data = data

    def upload_from_filename(self, filename: str) -> None:
        self.data = b"file"

    def open(self, mode: str) -> io.BytesIO:
        return io.BytesIO(self.data)


class Listing(list):
    prefixes: ClassVar[set[str]] = set()


class FakeGCS:
    def __init__(self, folders: set[str] | None = None, blobs: list | None = None) -> None:
        self.folders = folders or set()
        self.blobs = blobs or []
        self.uploaded: dict[str, FakeBlob] = {}

    def bucket(self, name: str) -> NS:
        def blob(path: str) -> FakeBlob:
            return self.uploaded.setdefault(path, FakeBlob(path))

        return NS(name=name, blob=blob)

    def list_blobs(self, bucket: str, prefix: str, delimiter: str | None = None) -> Listing:
        listing = Listing(b for b in self.blobs if b.name.startswith(prefix))
        listing.prefixes = self.folders
        return listing


def parquet(rows: int) -> bytes:
    return pd.DataFrame({"x": range(rows)}).to_parquet(index=False)


# 1_source -------------------------------------------------------------------------------


def test_settings_resolve_relative_key_path(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "GCP_PROJECT_ID=p\nGCS_BUCKET=b\nGOOGLE_APPLICATION_CREDENTIALS=secrets/k.json\n"
    )
    monkeypatch.setattr(config, "ENV_FILE", env)
    for name in ("GCP_PROJECT_ID", "GCS_BUCKET", "GOOGLE_APPLICATION_CREDENTIALS"):
        monkeypatch.delenv(name, raising=False)
    cfg = config.settings()
    assert cfg.project == "p"
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(config.ROOT / "secrets/k.json")


def test_clients_and_engine(cfg, monkeypatch) -> None:
    config.bq_client.cache_clear()
    config.gcs_client.cache_clear()
    monkeypatch.setattr(config.bigquery, "Client", lambda project: ("bq", project))
    monkeypatch.setattr(config.storage, "Client", lambda project: ("gcs", project))
    assert config.bq_client(cfg) == ("bq", "proj")
    assert config.gcs_client(cfg) == ("gcs", "proj")
    assert config.bq_client(cfg) is config.bq_client(cfg)  # cached per settings
    assert config.pg_engine(cfg).url.host == "h"
    with pytest.raises(RuntimeError, match="POSTGRES_URL"):
        config.pg_engine(config.Settings(GCP_PROJECT_ID="p", GCS_BUCKET="b", POSTGRES_URL=None))


def test_bq_helpers(cfg, tmp_path) -> None:
    assert bq.query_config(cfg).maximum_bytes_billed == cfg.max_bytes_billed
    client = FakeBQ({"t": NS()})
    assert bq.table_exists(client, "t")
    assert not bq.table_exists(client, "missing")
    sql = tmp_path / "q.sql"
    sql.write_text("SELECT 1 FROM `${project}.${bronze}.t`")
    assert bq.render_sql(sql, cfg) == "SELECT 1 FROM `proj.stylehub_bronze.t`"


def test_retry_waits_on_short_errors_only(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    calls = iter([exceptions.ServiceUnavailable("busy"), "ok"])

    def flaky() -> str:
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    assert retry.call_with_retry(flaky) == "ok"
    with pytest.raises(exceptions.NotFound):
        retry.call_with_retry(lambda: (_ for _ in ()).throw(exceptions.NotFound("gone")))
    reason = exceptions.BadRequest("x", errors=[{"reason": "rateLimitExceeded"}])
    assert retry.is_transient(reason)


def test_retry_gives_up_with_the_last_error(monkeypatch) -> None:
    def gives_up(**kwargs: object):
        def wrap(func):
            def call():
                raise exceptions.RetryError("timeout", cause=TimeoutError("late"))

            return call

        return wrap

    monkeypatch.setattr(retry, "Retry", gives_up)
    with pytest.raises(TimeoutError):
        retry.call_with_retry(lambda: None)


def test_load_csv_uploads_and_loads(cfg, tmp_path, monkeypatch) -> None:
    with pytest.raises(SystemExit):
        load_csv.find_csv_files(tmp_path)
    (tmp_path / "orders.csv").write_text("id\n1\n")
    gcs, client = FakeGCS(), FakeBQ({"proj.stylehub.orders": NS(num_rows=1, num_bytes=10)})
    monkeypatch.setattr(config, "gcs_client", lambda cfg: gcs)
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    monkeypatch.setattr(config, "settings", lambda: cfg)
    monkeypatch.setattr(load_csv, "DEFAULT_CSV_DIR", tmp_path)
    load_csv.main()
    assert "landing/stylehub/orders.csv" in gcs.uploaded
    assert client.calls[0][0] == "load"


# 2_ingestion ----------------------------------------------------------------------------


def test_schema_check_warns_and_fails() -> None:
    expected = schema_check.expected_schemas()["orders"]
    kinds = {"int": "INTEGER", "number": "FLOAT", "text": "STRING", "datetime": "TIMESTAMP"}
    fields = [NS(name=c, field_type=kinds[k]) for c, k in expected.items()]
    schema_check.check_declared_schema("orders", [*fields, NS(name="new", field_type="STRING")])
    schema_check.check_declared_schema("no_such_table", [])
    with pytest.raises(schema_check.SchemaError, match="missing columns"):
        schema_check.check_declared_schema("orders", fields[1:])
    retyped = [NS(name=fields[0].name, field_type="STRING"), *fields[1:]]
    with pytest.raises(schema_check.SchemaError, match="type changes"):
        schema_check.check_declared_schema("orders", retyped)
    empty = pd.DataFrame({"order_id": [None, None]})
    assert str(schema_check.type_empty_columns(empty, "orders")["order_id"].dtype) == "Int64"


def csv_source(rows: int) -> NS:
    expected = schema_check.expected_schemas()["orders"]
    kinds = {"int": "INTEGER", "number": "FLOAT", "text": "STRING", "datetime": "TIMESTAMP"}
    return NS(schema=[NS(name=c, field_type=kinds[k]) for c, k in expected.items()], num_rows=rows)


def test_csv_ingest_writes_raw(cfg, monkeypatch) -> None:
    frame = pd.DataFrame({"order_id": [1, 2]})
    client, gcs = FakeBQ({"proj.stylehub.orders": csv_source(2)}, frame), FakeGCS()
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    monkeypatch.setattr(config, "gcs_client", lambda cfg: gcs)
    assert csv_tables.ingest_table("orders", "2020-01-01", cfg) == 2  # old date also warns
    assert next(iter(gcs.uploaded)).startswith("raw/stylehub/orders/date=2020-01-01/")
    with pytest.raises(ValueError, match="No CSV table"):
        csv_tables.extract_full("events", cfg)
    client.tables["proj.stylehub.orders"] = csv_source(5)
    with pytest.raises(csv_tables.SourceRowMismatch):
        csv_tables.extract_full("orders", cfg)


class FakePg:
    """Engine whose connection returns a count and read_sql chunks."""

    def __init__(self, count: int) -> None:
        self.count = count

    def connect(self) -> "FakePg":
        return self

    def __enter__(self) -> "FakePg":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execution_options(self, **kwargs: object) -> "FakePg":
        return self

    def execute(self, query: object, params: dict) -> NS:
        return NS(scalar_one=lambda: self.count)


def test_postgres_incremental_ingest(cfg, monkeypatch) -> None:
    bronze = "proj.stylehub_bronze.pg_orders"
    client, gcs = FakeBQ({bronze: NS()}), FakeGCS()
    client.query_rows = [(datetime.fromisoformat("2026-10-14T23:00"),)]
    schema = pg_tables.arrow_schema("orders", [("id", "bigint"), ("total_amount", "numeric")])
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    monkeypatch.setattr(config, "gcs_client", lambda cfg: gcs)
    monkeypatch.setattr(config, "pg_engine", lambda cfg: FakePg(3))
    monkeypatch.setattr(pg_tables, "check_schema", lambda table, cfg: schema)  # tested below
    chunks = [
        pd.DataFrame({"id": [1, 2], "total_amount": [None, None]}),  # all NULL in this chunk
        pd.DataFrame({"id": [3], "total_amount": [Decimal("9.50")]}),
    ]
    asked: dict = {}

    def read_sql(*args: object, **kwargs: object) -> list[pd.DataFrame]:
        asked.update(kwargs)
        return chunks

    monkeypatch.setattr(pg_tables.pd, "read_sql", read_sql)
    assert pg_tables.ingest_table("orders", "2026-10-15", cfg) == 3
    assert asked["chunksize"] == pg_tables.CHUNK_ROWS
    assert "_PARTITIONDATE < DATE '2026-10-15'" in client.calls[0][1]
    files = sorted(gcs.uploaded)
    assert [p.rsplit("/", 1)[1] for p in files] == [
        "_SUCCESS",
        "part_00000.parquet",
        "part_00001.parquet",
    ]
    assert files[0].startswith("raw/stylehub/pg_orders/date=2026-10-15/batch_id=")
    paths = files[1:]
    # Every part has the same types, even a column that is NULL in one chunk.
    types = {
        str(pq.read_schema(io.BytesIO(gcs.uploaded[p].data)).field("total_amount").type)
        for p in paths
    }
    assert types == {"decimal128(38, 9)"}

    monkeypatch.setattr(config, "pg_engine", lambda cfg: FakePg(0))
    chunks = [pd.DataFrame({"id": []})]  # pandas yields one empty chunk when nothing matched
    client.tables.clear()  # first run: no Bronze table, full load
    gcs.uploaded.clear()
    assert pg_tables.ingest_table("orders", "2026-10-15", cfg) == 0
    assert not gcs.uploaded

    # Fewer rows than the source count: the part stays, but without _SUCCESS Bronze skips it.
    monkeypatch.setattr(config, "pg_engine", lambda cfg: FakePg(9))
    chunks = [pd.DataFrame({"id": [1], "total_amount": [None]})]
    end = datetime.fromisoformat("2026-10-16")
    with pytest.raises(pg_tables.SourceRowMismatch):
        pg_tables.extract_to_raw("orders", None, end, schema, "2026-10-15", cfg)
    assert list(gcs.uploaded) and not any(p.endswith("_SUCCESS") for p in gcs.uploaded)
    with pytest.raises(ValueError, match="No Postgres table"):
        pg_tables.extract_to_raw("events", None, end, schema, "2026-10-15", cfg)
    with pytest.raises(schema_check.SchemaError, match="jsonb"):
        pg_tables.arrow_schema("orders", [("id", "bigint"), ("meta", "jsonb")])


# 3_storage ------------------------------------------------------------------------------


def test_events_bronze_build(cfg, monkeypatch) -> None:
    client = FakeBQ({"proj.stylehub_bronze.events_raw": NS(num_rows=108)})
    client.copy_fails_in = {"asia-southeast1"}  # first region fails, then the source region
    built = {"done": False}
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    monkeypatch.setattr(config, "settings", lambda: cfg)
    monkeypatch.setattr(events_bronze, "events_table_exists", lambda cfg: built["done"])
    monkeypatch.setattr(events_bronze.retry, "call_with_retry", lambda func: func())

    def fake_query(sql: str, job_config: object = None) -> NS:
        built["done"] = True
        return job()

    client.query = fake_query
    events_bronze.main()
    assert ("delete", "proj.stylehub_bronze.events_raw") in client.calls
    client.calls.clear()
    events_bronze.ensure_events_bronze(cfg)  # already there: only a leftover copy is deleted
    assert client.calls == [("delete", "proj.stylehub_bronze.events_raw")]

    client.copy_fails_in = {"asia-southeast1", "US"}
    with pytest.raises(RuntimeError, match="either region"):
        events_bronze.copy_events(client, cfg)


def test_events_table_exists(cfg, monkeypatch) -> None:
    monkeypatch.setattr(config, "bq_client", lambda cfg: FakeBQ())
    assert not import_module("src.3_storage.events_bronze").events_table_exists(cfg)


def test_load_day_write_audit_publish(cfg, monkeypatch) -> None:
    prefix = "raw/stylehub/orders/date=2026-10-01/"
    gcs = FakeGCS(
        blobs=[
            FakeBlob(f"{prefix}batch_id=1/orders.parquet", parquet(5)),
            FakeBlob(f"{prefix}batch_id=2/orders.parquet", parquet(3)),  # newest, loaded
            FakeBlob(f"{prefix}batch_id=3/part_00000.parquet", parquet(1)),  # unfinished
        ]
    )
    client = FakeBQ({"proj.stylehub_bronze._stg_orders": NS(schema=[])})
    client.loaded_rows = 3
    monkeypatch.setattr(config, "gcs_client", lambda cfg: gcs)
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    assert load_bronze.load_day("orders", "2026-10-01", cfg, keep_days=None) == 3
    assert ("load", f"gs://bucket/{prefix}batch_id=2/*.parquet") in client.calls
    assert ("create", "orders", None) in client.calls
    assert ("copy", "proj.stylehub_bronze.orders$20261001", "asia-southeast1") in client.calls

    client.tables["proj.stylehub_bronze.orders"] = NS()  # existing table: no create
    client.loaded_rows = 2
    with pytest.raises(load_bronze.RowCountMismatch):
        load_bronze.load_day("orders", "2026-10-01", cfg)


def test_load_day_without_batches(cfg, monkeypatch) -> None:
    monkeypatch.setattr(config, "gcs_client", lambda cfg: FakeGCS())
    assert load_bronze.load_day("orders", "2026-10-02", cfg) == 0


def test_bronze_table_expiry_and_drop_staging(cfg) -> None:
    client = FakeBQ({"stg": NS(schema=[]), "proj.ds.exists": NS()})
    load_bronze.ensure_bronze_table(client, "proj.ds.exists", "stg", keep_days=30)
    assert client.calls == []  # an existing table is left alone
    load_bronze.ensure_bronze_table(client, "proj.ds.t", "stg", keep_days=30)
    assert client.calls[-1] == ("create", "t", 30 * 24 * 3600 * 1000)

    def broken(table_id: str, not_found_ok: bool) -> None:
        raise exceptions.Forbidden("no")

    client.delete_table = broken
    load_bronze.drop_staging(client, "stg")  # only warns


def test_record_run_writes_and_survives_errors(cfg, monkeypatch) -> None:
    client = FakeBQ()
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    now = datetime.now()  # noqa: DTZ005
    runs.record_run("r", "ingest", "2026-10-01", "success", now, now, 1, None, {"a": 1}, cfg)
    assert client.calls[0][1] == "proj.stylehub_ops.pipeline_runs"
    monkeypatch.setattr(config, "bq_client", lambda cfg: (_ for _ in ()).throw(RuntimeError("x")))
    runs.record_run("r", "ingest", "2026-10-01", "failed", now, now, None, "e", None, cfg)


# 4_transform ----------------------------------------------------------------------------


def dbt_result(*statuses: str) -> NS:
    results = [
        NS(node=NS(unique_id=f"model.m{i}"), status=NS(value=s)) for i, s in enumerate(statuses)
    ]
    return NS(results=results)


def test_run_dbt_summary_and_errors(monkeypatch) -> None:
    outcomes = iter(
        [
            NS(success=True, result=dbt_result("success", "warn"), exception=None),
            NS(success=False, result=dbt_result(*["error"] * 7), exception=None),
            NS(success=False, result=None, exception=RuntimeError("no profile")),
        ]
    )

    class Runner:
        def invoke(self, args: list[str]) -> NS:
            return next(outcomes)

    monkeypatch.setitem(sys.modules, "dbt.cli.main", NS(dbtRunner=Runner))
    summary = run_dbt.run_dbt("silver")
    assert summary == {"counts": {"success": 1, "warn": 1}, "warned": ["model.m1"]}
    with pytest.raises(run_dbt.DbtError, match="and 2 more"):
        run_dbt.run_dbt("gold")
    with pytest.raises(run_dbt.DbtError, match="no profile"):
        run_dbt.run_dbt("pg_silver")


def test_run_daily_runs_every_step(cfg, monkeypatch) -> None:
    recorded: list[tuple] = []
    monkeypatch.setattr(config, "settings", lambda: cfg)
    monkeypatch.setattr(run_daily.runs, "record_run", lambda *a: recorded.append((a[1], a[3])))
    monkeypatch.setattr(run_daily.csv_tables, "ingest_table", lambda t, d, c: 1)
    monkeypatch.setattr(run_daily.pg_tables, "ingest_table", lambda t, d, c: 2)
    monkeypatch.setattr(run_daily.events_bronze, "events_table_exists", lambda c: True)
    monkeypatch.setattr(run_daily.load_bronze, "load_day", lambda *a, **k: 3)
    monkeypatch.setattr(run_daily.run_dbt, "run_dbt", lambda layer: {"layer": layer})
    monkeypatch.setattr(run_daily.reconcile, "reconcile", lambda c: {"orders": 1})
    for step in run_daily.STEPS:
        run_daily.run_step("2026-10-01", step, "run-1")
    assert recorded == [(step, "success") for step in run_daily.STEPS]


def test_run_daily_records_failures(cfg, monkeypatch) -> None:
    recorded: list[tuple] = []
    monkeypatch.setattr(config, "settings", lambda: cfg)
    monkeypatch.setattr(run_daily.runs, "record_run", lambda *a: recorded.append(a[1:4]))
    monkeypatch.setattr(run_daily.events_bronze, "events_table_exists", lambda c: False)
    with pytest.raises(RuntimeError, match="events_partitioned is missing"):
        run_daily.run_step("2026-10-01", "bronze", "run-2")
    monkeypatch.setattr(run_daily.events_bronze, "events_table_exists", lambda c: True)
    monkeypatch.setattr(run_daily.load_bronze, "load_day", lambda *a, **k: 0)
    with pytest.raises(RuntimeError, match="no Raw file"):
        run_daily.run_step("2026-10-01", "bronze", "run-3")
    assert [(r[0], r[2]) for r in recorded] == [("bronze", "failed"), ("bronze", "failed")]


# dags -----------------------------------------------------------------------------------


def test_command_lines_pass_their_arguments(monkeypatch) -> None:
    freshness = import_module("src.5_serving.freshness")
    calls: list[tuple] = []
    monkeypatch.setattr(run_daily, "run_step", lambda *a: calls.append(("step", *a)))
    monkeypatch.setattr(freshness, "check", lambda *a: calls.append(("fresh", *a)))
    run_daily.main(["2026-10-01", "ingest", "gha-1"])
    monkeypatch.setattr(sys, "argv", ["freshness", "2026-10-01", "gha-1"])
    freshness.main()  # reads sys.argv like `python -m`
    assert calls == [("step", "2026-10-01", "ingest", "gha-1"), ("fresh", "2026-10-01", "gha-1")]


def test_scheduled_workflow_runs_the_dag_steps() -> None:
    """pipeline.yml must run the same steps, in the same order, as the Airflow DAG."""
    tree = ast.parse((config.ROOT / "dags" / "main_etl_dag.py").read_text(encoding="utf-8"))
    dag = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"CSV_STEPS", "PG_STEPS", "PG_ENABLED"}
    }
    workflow = yaml.safe_load((config.ROOT / ".github/workflows/pipeline.yml").read_text())
    assert workflow["env"]["CSV_STEPS"].split() == dag["CSV_STEPS"]
    assert workflow["env"]["PG_STEPS"].split() == (dag["PG_STEPS"] if dag["PG_ENABLED"] else [])
    assert set(dag["CSV_STEPS"] + dag["PG_STEPS"]) <= set(run_daily.STEPS)


def test_run_python_step_calls_run_daily(monkeypatch) -> None:
    utils_dag = import_module("dags.utils_dag")
    calls: list[tuple] = []
    monkeypatch.setattr(run_daily, "run_step", lambda *a: calls.append(a))
    utils_dag.run_python_step("2026-10-01", "ingest", str(config.ROOT), "run-9")
    assert calls == [("2026-10-01", "ingest", "run-9")]


def test_logger_is_set_up_once() -> None:
    logger = import_module("src.0_utils.logger")
    first = logger.get_logger("tests.once")
    assert logger.get_logger("tests.once") is first
    assert len(first.handlers) == 2


def test_log_file_moves_to_the_new_day(tmp_path, monkeypatch) -> None:
    logger = import_module("src.0_utils.logger")
    monkeypatch.setattr(logger, "LOG_DIR", tmp_path)
    days = iter(["2026-01-01", "2026-01-01", "2026-01-02"])
    monkeypatch.setattr(logger, "today", lambda: next(days))
    handler = logger.DailyFileHandler("unified-data_test_mod")
    record = logging.LogRecord("mod", logging.INFO, __file__, 1, "hello", None, None)
    handler.emit(record)  # same day
    handler.emit(record)  # after midnight: new file
    handler.close()
    assert sorted(f.name for f in tmp_path.iterdir()) == [
        "unified-data_test_mod_2026-01-01.log",
        "unified-data_test_mod_2026-01-02.log",
    ]


def test_alerts_message_and_send(monkeypatch) -> None:
    alerts = import_module("src.0_utils.alerts")
    text = alerts.failure_message("stylehub_daily", "pg_gold", "run-1", "boom", "http://log")
    assert "task `pg_gold` failed" in text and "Log: http://log" in text
    assert "the DAG run failed" in alerts.failure_message("d", None, "r", "timeout", None)

    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert alerts.send_alert("x") is False  # no webhook: log only

    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://discord.test/hook")
    posted: list[dict] = []
    ok = NS(raise_for_status=lambda: None)
    post = lambda url, json, timeout: posted.append(json) or ok  # noqa: E731
    monkeypatch.setattr(alerts.requests, "post", post)
    assert alerts.send_alert("y" * 5000) is True
    assert len(posted[0]["content"]) == alerts.MAX_CHARS

    def refuse(*args: object, **kwargs: object) -> NS:
        raise alerts.requests.ConnectionError("down")

    monkeypatch.setattr(alerts.requests, "post", refuse)
    assert alerts.send_alert("z") is False


def test_dag_helpers_run_freshness_and_alert(monkeypatch) -> None:
    utils_dag = import_module("dags.utils_dag")
    freshness = import_module("src.5_serving.freshness")
    alerts = import_module("src.0_utils.alerts")
    checked: list[tuple] = []
    monkeypatch.setattr(freshness, "check", lambda *a: checked.append(a))
    utils_dag.run_freshness_check("2026-10-01", str(config.ROOT), "run-2")
    assert checked == [("2026-10-01", "run-2")]

    sent: list[str] = []
    monkeypatch.setattr(alerts, "send_alert", sent.append)
    ti = NS(task_id="bronze", log_url="http://log")
    run = NS(dag_id="stylehub_daily", run_id="run-3")
    utils_dag.alert_on_failure({"ti": ti, "dag_run": run, "exception": ValueError("bad\nmore")})
    utils_dag.alert_on_failure({"dag_run": run, "reason": "timed_out"})
    assert "task `bronze` failed" in sent[0] and "Error: bad" in sent[0]
    assert "the DAG run failed" in sent[1] and "timed_out" in sent[1]


def test_freshness_check_records_and_alerts(cfg, monkeypatch) -> None:
    freshness = import_module("src.5_serving.freshness")
    client = FakeBQ()
    monkeypatch.setattr(freshness.config, "settings", lambda: cfg)
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    recorded: list[tuple] = []
    sent: list[str] = []
    monkeypatch.setattr(freshness.runs, "record_run", lambda *a: recorded.append(a))
    monkeypatch.setattr(freshness.alerts, "send_alert", sent.append)

    client.query_rows = [NS(table_name="orders", hours_old=3)]
    freshness.check("2026-10-01", "run-4")
    assert recorded[-1][3] == "success" and not sent

    client.query_rows = [NS(table_name="orders", hours_old=3), NS(table_name="users", hours_old=40)]
    with pytest.raises(RuntimeError, match="users"):
        freshness.check("2026-10-01", "run-5")
    assert recorded[-1][3] == "failed" and "users (40 h)" in sent[0]


def test_reconcile_writes_the_deleted_ids(cfg, monkeypatch) -> None:
    reconcile = import_module("src.3_storage.reconcile")
    client = FakeBQ()
    client.query_rows = [NS(id=1), NS(id=2), NS(id=3)]  # Bronze ids of every table
    loaded: list = []
    client.load_table_from_dataframe = lambda df, target, job_config: (
        loaded.append((target, df, job_config.write_disposition)) or job()
    )
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)

    class Conn(FakePg):
        def execute(self, query: object, params: dict | None = None) -> NS:
            return NS(scalars=lambda: iter([1, 3]))  # Postgres lost id 2

    monkeypatch.setattr(config, "pg_engine", lambda cfg: Conn(0))
    counts = reconcile.reconcile(cfg)
    assert counts == dict.fromkeys(pg_tables.PG_TABLES, 1)
    target, frame, disposition = loaded[0]
    assert target == "proj.stylehub_bronze.pg_deleted_ids" and disposition == "WRITE_TRUNCATE"
    assert sorted(frame["table_name"]) == sorted(pg_tables.PG_TABLES)
    assert set(frame["id"]) == {2}

    # Next day: ids flagged before keep their first detected_at.
    first_seen = pd.Timestamp("2026-10-01", tz="UTC")
    client.tables[target] = NS()
    flagged = pd.DataFrame({"table_name": ["orders"], "id": [2], "detected_at": [first_seen]})
    client.list_rows = lambda table, selected_fields: NS(to_dataframe=lambda: flagged)
    reconcile.reconcile(cfg)
    frame = loaded[-1][1].set_index("table_name")["detected_at"]
    assert frame["orders"] == first_seen and frame["users"] > first_seen


def test_postgres_schema_check(cfg, monkeypatch) -> None:
    pg_types = {"int": "bigint", "number": "numeric", "text": "text"}
    pg_types["datetime"] = "timestamp without time zone"
    expected = schema_check.expected_schemas("stylehub_pg")["pg_orders"]
    columns = [(c, pg_types[k]) for c, k in expected.items()]

    class Conn(FakePg):
        def execute(self, query: object, params: dict | None = None) -> NS:
            return NS(all=lambda: columns)

    monkeypatch.setattr(config, "pg_engine", lambda cfg: Conn(0))
    schema = pg_tables.check_schema("orders", cfg)  # matches the sources file
    assert schema.names == list(expected) and str(schema.field("total_amount").type) == (
        "decimal128(38, 9)"
    )
    columns[2] = (columns[2][0], "text")  # total_amount turned into text
    with pytest.raises(schema_check.SchemaError, match="type changes"):
        pg_tables.check_schema("orders", cfg)
