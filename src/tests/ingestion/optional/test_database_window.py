from datetime import date

from ingestion.optional.database import window_for


def test_window_covers_lookback_and_whole_day():
    start, end = window_for(date(2026, 10, 5), lookback_days=1)
    assert start.isoformat() == "2026-10-04T00:00:00"
    assert end.isoformat() == "2026-10-06T00:00:00"
