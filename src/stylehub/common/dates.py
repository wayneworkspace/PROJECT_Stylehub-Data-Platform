"""The data date is a plain string YYYY-MM-DD. Check it once, at the door of the pipeline.

A wrong date would otherwise travel into GCS paths and BigQuery before anything complains.
"""

import argparse
from datetime import date, timedelta

# Session 2: an incremental load re-reads this many days before the data date, so rows that
# were written late are not missed. The duplicates are removed in Silver.
LOOKBACK_DAYS = 1


def valid_date(value: str) -> str:
    """Return the value if it is a real date written as YYYY-MM-DD, else raise ValueError."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise ValueError(f"not a date in the form YYYY-MM-DD: {value!r}")
    return value


def date_arg(value: str) -> str:
    """The same check for argparse: add_argument("--date", type=date_arg)."""
    try:
        return valid_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def backfill_dates(end: str, days: int) -> list[str]:
    """The `days` dates that end at `end`, oldest first. Backfill = run each of them again."""
    last = date.fromisoformat(valid_date(end))
    return [(last - timedelta(days=n)).isoformat() for n in range(days - 1, -1, -1)]


def watermark_window(data_date: str, lookback_days: int = LOOKBACK_DAYS) -> tuple[str, str]:
    """The first and the last day (both included) that an incremental load reads."""
    last = date.fromisoformat(valid_date(data_date))
    return (last - timedelta(days=lookback_days)).isoformat(), last.isoformat()
