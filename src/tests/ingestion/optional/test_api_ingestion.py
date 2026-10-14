from datetime import date

import pandas as pd
import pytest

from ingestion.optional import api


def user_row(user_id, email):
    """A user with every column that EXPECTED_SCHEMAS asks for."""
    return {
        "id": user_id,
        "email": email,
        "gender": "F",
        "state": "Texas",
        "city": "Austin",
        "country": "USA",
        "latitude": 30.2,
        "longitude": -97.7,
        "traffic_source": "Search",
        "created_at": pd.Timestamp("2026-10-01"),
    }


@pytest.fixture
def source_rows(monkeypatch):
    """Replace the API call. Remember what was asked."""
    asked = []

    def fake_fetch_rows(endpoint, params):
        asked.append((endpoint, params))
        return [user_row(1, "a@example.org"), user_row(2, "b@example.org")]

    monkeypatch.setattr(api, "fetch_rows", fake_fetch_rows)
    return asked


def test_day_params_ask_for_one_day():
    assert api.day_params(date(2026, 10, 1)) == {
        "created_from": "2026-10-01",
        "created_to": "2026-10-01",
    }


def test_extract_day_calls_the_endpoint_of_the_table(source_rows):
    df = api.extract_day("users", date(2026, 10, 1))
    assert len(df) == 2
    assert source_rows == [("stylehub-users", api.day_params(date(2026, 10, 1)))]


def test_an_unknown_table_is_refused(source_rows):
    with pytest.raises(ValueError, match="No API endpoint"):
        api.extract_day("orders", date(2026, 10, 1))
    assert source_rows == []


def test_dry_run_counts_rows_and_writes_nothing(source_rows, monkeypatch):
    def must_not_write(*args, **kwargs):
        raise AssertionError("write_raw must not run in a dry run")

    monkeypatch.setattr(api, "write_raw", must_not_write)
    message = api.ingest_table("users", "2026-10-01", dry_run=True)
    assert "2 rows" in message
    assert "dry run" in message


def test_a_normal_run_writes_one_raw_file_with_the_api_as_source(source_rows, monkeypatch):
    written = []

    def fake_write_raw(df, table, data_date, source):
        written.append((len(df), table, data_date, source))
        return "gs://fake/users"

    monkeypatch.setattr(api, "write_raw", fake_write_raw)
    message = api.ingest_table("users", "2026-10-01")
    assert written == [(2, "users", "2026-10-01", "stylehub_api")]
    assert "gs://fake/users" in message
