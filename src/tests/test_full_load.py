from datetime import date

import pandas as pd
import pytest

from ingestion import database


@pytest.fixture
def queries(monkeypatch):
    """Replace the database call and remember every query that was asked."""
    asked = []

    def fake_fetch(query, params=()):
        asked.append((query, params))
        return pd.DataFrame({"id": [1]})

    monkeypatch.setattr(database, "fetch_dataframe", fake_fetch)
    return asked


def test_full_load_reads_the_whole_table(queries):
    database.extract_full("orders")
    assert queries == [("SELECT * FROM orders", ())]


def test_incremental_reads_only_the_window(queries):
    database.extract_day("orders", date(2026, 10, 1))
    query, params = queries[0]
    assert "WHERE updated_at >= %s AND updated_at < %s" in query
    assert [p.isoformat() for p in params] == ["2026-09-30T00:00:00", "2026-10-02T00:00:00"]


def test_unknown_table_is_refused_in_both_modes(queries):
    with pytest.raises(ValueError):
        database.extract_full("users; DROP TABLE orders")
    with pytest.raises(ValueError):
        database.extract_day("users", date(2026, 10, 1))
    assert queries == []  # nothing reached the database


def test_full_load_message_says_so(monkeypatch):
    from tests.test_schema_check import sample_frame

    monkeypatch.setattr(database, "extract_full", lambda table: sample_frame("orders"))
    message = database.ingest_table("orders", "2026-10-01", dry_run=True, full_load=True)
    assert "2 rows" in message and "full load" in message and "dry run" in message


def test_schema_change_stops_before_anything_is_written(monkeypatch):
    from ingestion.schema_check import SchemaError
    from tests.test_schema_check import sample_frame

    monkeypatch.setattr(
        database, "extract_day", lambda t, d: sample_frame("orders").drop(columns=["status"])
    )

    def must_not_write(*args, **kwargs):
        raise AssertionError("write_raw must not run when the schema is wrong")

    monkeypatch.setattr(database, "write_raw", must_not_write)
    with pytest.raises(SchemaError, match="status"):
        database.ingest_table("orders", "2026-10-01")
