from collections import defaultdict
from datetime import date

import pytest

from ingestion import incremental
from pipeline import backfill, run_daily
from tests.test_schema_check import sample_frame


def test_date_range_includes_both_ends_oldest_first():
    days = backfill.date_range(date(2026, 9, 29), date(2026, 10, 2))
    assert [d.isoformat() for d in days] == ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]


def test_date_range_of_one_day():
    assert backfill.date_range(date(2026, 10, 1), date(2026, 10, 1)) == [date(2026, 10, 1)]


def test_date_range_rejects_a_backwards_range():
    with pytest.raises(ValueError):
        backfill.date_range(date(2026, 10, 2), date(2026, 10, 1))


@pytest.fixture
def raw_zone(monkeypatch):
    """A fake source and a fake Raw Zone. Every write adds one file, like GCS does."""
    files = []  # one entry per raw file: (table, data_date, ids in the file)

    def fake_extract_day(table, data_date):
        # Ids depend on the day. The last id of the day before is read again (the lookback).
        first = data_date.day * 10
        return sample_frame(table, ids=range(first - 1, first + 5))

    def fake_write_raw(df, table, data_date, source):
        files.append((table, data_date, tuple(df["id"])))
        return f"gs://fake/{table}/date={data_date}/batch_id={len(files)}"

    monkeypatch.setattr(incremental, "extract_day", fake_extract_day)
    monkeypatch.setattr(incremental, "write_raw", fake_write_raw)
    monkeypatch.setattr(run_daily, "record_run", lambda row: True)
    monkeypatch.setattr(run_daily, "send_alert", lambda text: True)
    return files


def distinct_ids_per_day(files):
    ids = defaultdict(set)
    for table, data_date, file_ids in files:
        ids[(table, data_date)].update(file_ids)
    return {key: len(value) for key, value in ids.items()}


def test_backfill_twice_adds_files_but_not_distinct_ids(raw_zone):
    start, end = date(2026, 9, 25), date(2026, 10, 1)  # 7 days, like the homework

    backfill.backfill(start, end)
    after_first = distinct_ids_per_day(raw_zone)
    files_after_first = len(raw_zone)

    backfill.backfill(start, end)  # run the whole range again

    assert files_after_first == 7 * len(incremental.INCREMENTAL_TABLES)
    assert len(raw_zone) == 2 * files_after_first  # append-only: every run writes new files
    assert distinct_ids_per_day(raw_zone) == after_first  # but the distinct ids did not change
    assert len(after_first) == files_after_first  # every (table, day) has data


def test_backfill_stops_at_the_first_failed_date(raw_zone, monkeypatch):
    def fail_on_the_27th(table, data_date):
        if data_date.day == 27:
            raise RuntimeError("source is down")
        return sample_frame(table, ids=[1])

    monkeypatch.setattr(incremental, "extract_day", fail_on_the_27th)
    with pytest.raises(RuntimeError):
        backfill.backfill(date(2026, 9, 25), date(2026, 9, 29))
    days_written = {data_date for _, data_date, _ in raw_zone}
    assert days_written == {"2026-09-25", "2026-09-26"}  # later days were not tried
