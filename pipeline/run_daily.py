"""Run the whole pipeline for one date, step by step. Each step is its own function.

When moving to Airflow later, each entry in STEPS becomes a task,
with no change to the logic inside.

Every step is logged, recorded in BigQuery (pipeline_runs) and sends an alert if it fails.

Usage: python -m pipeline.run_daily --date 2026-10-01 [--from-step bronze] [--to-step ingest]
"""

import argparse
import logging
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from ingestion.incremental import INCREMENTAL_TABLES, ingest_table
from pipeline.alerts import send_alert
from pipeline.checks import run_checks
from pipeline.load_bronze import TABLES, load_day
from pipeline.run_sql import run_layer
from pipeline.runs import record_run, run_row

log = logging.getLogger("pipeline")

MAX_ERROR_CHARS = 500  # Longer errors are cut, so one pipeline_runs row stays small.


def step_ingest(data_date: str) -> int | None:
    for table in INCREMENTAL_TABLES:
        log.info(ingest_table(table, data_date))
    return None


def step_bronze(data_date: str) -> int | None:
    total = 0
    for table in TABLES:
        rows = load_day(table, data_date)
        log.info("%s: %s rows", table, rows)
        total += rows
    return total


def step_silver(data_date: str) -> int | None:
    run_layer("silver")
    return None


def step_gold(data_date: str) -> int | None:
    run_layer("gold")
    return None


def step_checks(data_date: str) -> int | None:
    if not run_checks():
        raise SystemExit("Data checks failed")
    return None


# A step takes the data date and returns the rows it loaded, or None if it does not count rows.
STEPS = [
    ("ingest", step_ingest),
    ("bronze", step_bronze),
    ("silver", step_silver),
    ("gold", step_gold),
    ("checks", step_checks),
]


def run_step(
    run_id: str, name: str, func: Callable[[str], int | None], data_date: str
) -> None:
    """Run one step. Record it and alert on failure. Re-raise the error so the run stops."""
    started = datetime.now(UTC)
    status, rows, error = "success", None, None
    log.info("[run %s] step %s starts for %s", run_id, name, data_date)
    try:
        rows = func(data_date)
    except (Exception, SystemExit) as exc:
        status, error = "failed", (str(exc) or type(exc).__name__)[:MAX_ERROR_CHARS]
        log.error("[run %s] step %s FAILED: %s", run_id, name, error)
        raise
    finally:
        finished = datetime.now(UTC)
        record_run(run_row(run_id, name, data_date, status, started, finished, rows, error))
        if status == "failed":
            send_alert(
                f"StyleHub pipeline FAILED\nstep: {name}\ndate: {data_date}\n"
                f"run: {run_id}\nerror: {error}"
            )
    log.info("[run %s] step %s done in %.1fs", run_id, name, (finished - started).total_seconds())


def setup_logging() -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main() -> None:
    names = [name for name, _ in STEPS]
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--from-step", choices=names, default=names[0])
    parser.add_argument("--to-step", choices=names, default=names[-1])
    args = parser.parse_args()
    first, last = names.index(args.from_step), names.index(args.to_step)
    if first > last:
        parser.error("--from-step must come before --to-step")

    setup_logging()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    for name, func in STEPS[first : last + 1]:
        run_step(run_id, name, func, args.date)


if __name__ == "__main__":
    main()
