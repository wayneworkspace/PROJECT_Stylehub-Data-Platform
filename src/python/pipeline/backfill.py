"""Run the pipeline for a range of past dates (backfill, session 2).

Each date is a "logical date": the day whose data we load, not the day we run. Use it when the
pipeline was down for a few days, or after a bug fix. Dates run from the oldest to the newest.
A failed date stops the backfill, so you can fix the problem and start again from that date.

Every date goes through run_step, so it is logged, recorded in pipeline_runs and alerted like a
normal daily run. Running the same range twice is safe: Raw gets new files, but the number of
distinct ids does not change (src/tests/test_backfill.py proves it).

By default only the ingest step runs. Then run Silver and Gold once for the whole range.

Usage:
    python -m pipeline.backfill --from-date 2026-09-25 --to-date 2026-10-01
    python -m pipeline.backfill --from-date 2026-09-25 --to-date 2026-10-01 --to-step bronze
"""

import argparse
import logging
from datetime import date, timedelta

from pipeline import run_daily

log = logging.getLogger("pipeline")


def date_range(start: date, end: date) -> list[date]:
    """Every date from start to end, both included, oldest first."""
    if start > end:
        raise ValueError(f"start ({start}) must not be after end ({end})")
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def backfill(start: date, end: date, first_step: str = "ingest", last_step: str = "ingest") -> None:
    dates = date_range(start, end)
    log.info("Backfill of %s dates, %s to %s, steps %s to %s",
             len(dates), start, end, first_step, last_step)
    for data_date in dates:
        run_daily.run_steps(data_date.isoformat(), first_step, last_step)


def main() -> None:
    names = [name for name, _ in run_daily.STEPS]
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--from-step", choices=names, default="ingest")
    parser.add_argument("--to-step", choices=names, default="ingest")
    args = parser.parse_args()
    if names.index(args.from_step) > names.index(args.to_step):
        parser.error("--from-step must come before --to-step")
    if args.from_date > args.to_date:
        parser.error("--from-date must not be after --to-date")

    run_daily.setup_logging()
    backfill(args.from_date, args.to_date, args.from_step, args.to_step)


if __name__ == "__main__":
    main()
