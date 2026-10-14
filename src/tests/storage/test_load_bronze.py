"""Bronze keeps one batch per day: a re-run must not double the rows."""

import pytest

from storage import load_bronze
from storage.load_bronze import batch_ids_from_names

PREFIX = "raw/stylehub/orders/date=2026-10-01/"


def names(*batch_ids: str) -> list[str]:
    return [f"{PREFIX}batch_id={b}/orders.parquet" for b in batch_ids]


def test_batch_ids_are_sorted_oldest_first():
    found = batch_ids_from_names(names("20261001T030000-bbbbbb", "20261001T020000-aaaaaa"))
    assert found == ["20261001T020000-aaaaaa", "20261001T030000-bbbbbb"]


def test_batch_ids_ignore_files_without_a_batch():
    assert batch_ids_from_names([f"{PREFIX}readme.txt"]) == []


class FakeJob:
    output_rows = 10

    def result(self):
        return self


class FakeClient:
    def __init__(self):
        self.events = []  # the order of "load" and "delete" actions
        self.fail = False

    def load_table_from_uri(self, uri, table_id, job_config):
        if self.fail:
            raise RuntimeError("load failed")
        self.events.append(("load", uri))
        return FakeJob()


def prepare(monkeypatch, batches, in_bronze, exists=True):
    """Fake GCS and BigQuery. `in_bronze` is the rows of the latest batch already loaded."""
    client = FakeClient()
    events = client.events
    monkeypatch.setenv("GCP_PROJECT_ID", "p")
    monkeypatch.setenv("GCS_BUCKET", "b")
    monkeypatch.setattr(load_bronze.bigquery, "Client", lambda project: client)
    monkeypatch.setattr(load_bronze, "list_batch_ids", lambda prefix: batches)
    monkeypatch.setattr(load_bronze, "table_exists", lambda c, t: exists)
    monkeypatch.setattr(load_bronze, "count_batch_rows", lambda c, t, b: in_bronze)
    monkeypatch.setattr(
        load_bronze, "delete_batches", lambda c, t, ids: events.append(("delete", ids))
    )
    return client, events


def test_new_batch_is_loaded_before_the_older_batch_is_deleted(monkeypatch):
    client, events = prepare(monkeypatch, ["a", "b"], in_bronze=0)
    assert load_bronze.load_day("orders", "2026-10-01") == 10
    assert events == [("load", f"gs://b/{PREFIX}batch_id=b/*"), ("delete", ["a"])]


def test_a_failed_load_keeps_the_older_batch(monkeypatch):
    client, events = prepare(monkeypatch, ["a", "b"], in_bronze=0)
    client.fail = True
    with pytest.raises(RuntimeError):
        load_bronze.load_day("orders", "2026-10-01")
    assert ("delete", ["a"]) not in events


def test_same_batch_is_not_loaded_twice(monkeypatch):
    client, events = prepare(monkeypatch, ["a"], in_bronze=100)
    assert load_bronze.load_day("orders", "2026-10-01") == 0
    assert events == []


def test_leftover_older_batch_is_removed_even_when_the_new_one_is_loaded(monkeypatch):
    client, events = prepare(monkeypatch, ["a", "b"], in_bronze=100)
    assert load_bronze.load_day("orders", "2026-10-01") == 0
    assert events == [("delete", ["a"])]


def test_first_load_creates_the_table(monkeypatch):
    client, events = prepare(monkeypatch, ["a"], in_bronze=0, exists=False)
    assert load_bronze.load_day("orders", "2026-10-01") == 10
    assert events == [("load", f"gs://b/{PREFIX}batch_id=a/*")]


def test_no_raw_files_loads_nothing(monkeypatch):
    client, events = prepare(monkeypatch, [], in_bronze=0)
    assert load_bronze.load_day("orders", "2026-10-01") == 0
    assert events == []
