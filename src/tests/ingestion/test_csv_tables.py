"""The CSV path is the one that run_daily uses every day."""

from datetime import date
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from stylehub.ingestion import csv_tables, runner
from stylehub.ingestion.schema_check import EXPECTED_SCHEMAS, SchemaError
from tests.ingestion.test_schema_check import sample_frame

BQ_TYPE = {"int": "INTEGER", "number": "FLOAT", "text": "STRING", "datetime": "TIMESTAMP"}


def source_table(table, rows=2, extra=(), drop=(), retype=None):
    """What client.get_table() says about the source table: its columns and its row count."""
    retype = retype or {}
    schema = [
        bigquery.SchemaField(col, retype.get(col, BQ_TYPE[kind]))
        for col, kind in EXPECTED_SCHEMAS[table].items()
        if col not in drop
    ]
    schema += [bigquery.SchemaField(name, kind) for name, kind in extra]
    return MagicMock(schema=schema, num_rows=rows)


def test_extract_full_reads_the_whole_table_and_drops_the_geometry_column(monkeypatch):
    client = MagicMock()
    client.get_table.return_value = source_table("users", extra=[("user_geom", "GEOGRAPHY")])
    client.query.return_value.to_dataframe.return_value = sample_frame("users").assign(
        user_geom="POINT(1 2)"
    )
    monkeypatch.setattr(csv_tables.bigquery, "Client", lambda project: client)

    df = csv_tables.extract_full("users")

    assert "user_geom" not in df.columns
    assert client.query.call_args.args[0] == "SELECT * FROM `my-project.stylehub.users`"


def test_an_unknown_table_is_refused():
    with pytest.raises(ValueError, match="No CSV table"):
        csv_tables.extract_full("events")


def test_dry_run_counts_rows_and_writes_nothing(monkeypatch):
    monkeypatch.setattr(csv_tables, "extract_full", lambda table, **kwargs: sample_frame("orders"))

    def must_not_write(*args, **kwargs):
        raise AssertionError("write_raw must not run in a dry run")

    monkeypatch.setattr(runner, "write_raw", must_not_write)
    message = str(csv_tables.ingest_table("orders", "2026-10-01", dry_run=True))
    assert "2 rows" in message and "csv" in message and "dry run" in message


def test_a_normal_run_writes_one_raw_file_with_csv_as_source(monkeypatch):
    monkeypatch.setattr(csv_tables, "extract_full", lambda table, **kwargs: sample_frame("orders"))
    written = []

    def fake_write_raw(df, table, data_date, source):
        written.append((len(df), table, data_date, source))
        return "gs://fake/orders"

    monkeypatch.setattr(runner, "write_raw", fake_write_raw)
    message = str(csv_tables.ingest_table("orders", "2026-10-01"))
    assert written == [(2, "orders", "2026-10-01", "csv")]
    assert "gs://fake/orders" in message


def test_a_schema_change_stops_before_anything_is_written(monkeypatch):
    broken = sample_frame("orders").drop(columns=["status"])
    monkeypatch.setattr(csv_tables, "extract_full", lambda table, **kwargs: broken)

    def must_not_write(*args, **kwargs):
        raise AssertionError("write_raw must not run when the schema is wrong")

    monkeypatch.setattr(runner, "write_raw", must_not_write)
    with pytest.raises(SchemaError, match="status"):
        csv_tables.ingest_table("orders", "2026-10-01")


def test_the_result_holds_the_numbers_and_the_log_sentence(monkeypatch):
    monkeypatch.setattr(csv_tables, "extract_full", lambda table, **kwargs: sample_frame("orders"))
    monkeypatch.setattr(runner, "write_raw", lambda df, table, d, source: "gs://fake/orders")

    result = csv_tables.ingest_table("orders", "2026-10-01")

    assert (result.rows, result.table, result.mode) == (2, "orders", "csv")
    assert result.uri == "gs://fake/orders"
    assert str(result).startswith("orders 2026-10-01: 2 rows (csv, ")


def test_a_wrong_date_is_refused_before_anything_is_read(monkeypatch):
    def must_not_read(table, **kwargs):
        raise AssertionError("nothing may be read for a wrong date")

    monkeypatch.setattr(csv_tables, "extract_full", must_not_read)
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        csv_tables.ingest_table("orders", "01/10/2026")


def test_extract_full_uses_the_client_it_is_given():
    client = MagicMock()
    client.get_table.return_value = source_table("orders")
    client.query.return_value.to_dataframe.return_value = sample_frame("orders")
    csv_tables.extract_full("orders", client=client)
    assert client.query.call_args.args[0] == "SELECT * FROM `my-project.stylehub.orders`"


def test_a_changed_source_table_stops_before_any_row_is_read():
    client = MagicMock()
    client.get_table.return_value = source_table("orders", drop=["status"])
    with pytest.raises(SchemaError, match="status"):
        csv_tables.extract_full("orders", client=client)
    client.query.assert_not_called()


def test_a_retyped_source_column_stops_before_any_row_is_read():
    client = MagicMock()
    client.get_table.return_value = source_table("users", retype={"age": "STRING"})
    with pytest.raises(SchemaError, match="age"):
        csv_tables.extract_full("users", client=client)
    client.query.assert_not_called()


def test_absorb_mode_does_not_stop_on_the_declared_columns():
    client = MagicMock()
    client.get_table.return_value = source_table("orders", drop=["status"])
    client.query.return_value.to_dataframe.return_value = sample_frame("orders")
    csv_tables.extract_full("orders", client=client, on_schema_change="absorb")
    client.query.assert_called_once()


def test_fewer_rows_read_than_the_source_has_is_an_error():
    client = MagicMock()
    client.get_table.return_value = source_table("orders", rows=5)
    client.query.return_value.to_dataframe.return_value = sample_frame("orders")  # 2 rows
    with pytest.raises(csv_tables.SourceRowMismatch, match="read 2 rows, the source has 5"):
        csv_tables.extract_full("orders", client=client)


def test_a_label_older_than_a_few_days_warns(caplog):
    today = date(2026, 10, 16)
    assert runner.warn_if_backdated("2026-10-01", today=today) is True
    assert "read as it is TODAY" in caplog.text
    assert runner.warn_if_backdated("2026-10-15", today=today) is False
