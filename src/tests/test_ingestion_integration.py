"""Run the extraction against a real Postgres that holds docker/postgres/init/01_seed.sql.

Start it with `docker compose up -d postgres`, then run:
    pytest -m integration
with PG_HOST, PG_PORT, PG_DATABASE, PG_USER and PG_PASSWORD pointing at it.
"""

from datetime import date

import pytest

from ingestion.database import extract_day, extract_full, ingest_table

pytestmark = pytest.mark.integration


def test_orders_window_includes_lookback_and_late_update():
    df = extract_day("orders", date(2026, 10, 1))
    ids = set(df["id"])
    assert ids == set(range(1, 24)) | {100}


def test_orders_window_excludes_old_rows():
    df = extract_day("orders", date(2026, 10, 1))
    assert 101 not in set(df["id"])


def test_order_items_window():
    df = extract_day("order_items", date(2026, 10, 1))
    assert set(df["id"]) == set(range(1, 47))


def test_amount_matches_price_times_quantity():
    df = extract_day("order_items", date(2026, 10, 1))
    assert (df["amount"] == df["sale_price"] * df["quantity"]).all()


def test_full_load_returns_every_row():
    df = extract_full("orders")
    assert set(df["id"]) == set(range(1, 31)) | {100, 101}


def test_seed_data_passes_the_schema_check():
    for table in ("orders", "order_items"):
        message = ingest_table(table, "2026-10-01", dry_run=True)  # raises if the schema is off
        assert "dry run" in message


def test_dry_run_writes_nothing(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("write_raw must not run in a dry run")

    monkeypatch.setattr("ingestion.database.write_raw", fail)
    message = ingest_table("orders", "2026-10-01", dry_run=True)
    assert "24 rows" in message
    assert "dry run" in message
