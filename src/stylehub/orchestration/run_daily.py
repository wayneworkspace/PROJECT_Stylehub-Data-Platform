"""Run the whole pipeline for one date, step by step. Each step is its own function.

Airflow runs the same steps, one task per step (see deploy/airflow/dags/stylehub_daily.py).
Silver and Gold are built by dbt, which also runs the tests, so there is no separate checks step.

Every step is logged and recorded in BigQuery (pipeline_runs).

Usage:
    python -m stylehub.orchestration.run_daily --date 2026-10-01 \
        [--from-step bronze] [--to-step gold]
"""

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from stylehub.bronze.events_bronze import EVENTS_BOOTSTRAP_COMMAND, events_table_exists
from stylehub.bronze.load_bronze import load_day
from stylehub.common.dates import date_arg, valid_date
from stylehub.common.ids import new_id
from stylehub.common.logs import PIPELINE_FORMAT, setup_cli_logging
from stylehub.ingestion import csv_tables
from stylehub.orchestration.runs import record_run, run_row
from stylehub.transform.run_dbt import run_dbt

log = logging.getLogger("pipeline")

MAX_ERROR_CHARS = 500  # Longer errors are cut, so one pipeline_runs row stays small.


@dataclass(frozen=True)
class StepOutcome:
    """What a step returns.

    rows goes to pipeline_runs.rows_loaded. detail (rows per table, dbt test counts, ...) goes to
    pipeline_runs.detail as JSON.
    """

    rows: int | None = None
    detail: dict[str, Any] | None = None


def step_ingest(data_date: str) -> StepOutcome:
    # The course data comes from CSV files: full load, no watermark.
    # The old Postgres and API sources were removed from the package.
    by_table: dict[str, int] = {}
    for table in csv_tables.CSV_TABLES:
        result = csv_tables.ingest_table(table, data_date)
        log.info("%s", result)
        by_table[table] = result.rows
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_bronze(data_date: str) -> StepOutcome:
    # events is a one-time build (15 GB copy), so it is NOT part of the daily run. If it is
    # missing, stop here with a clear message instead of letting Silver fail later.
    if not events_table_exists():
        raise RuntimeError(
            f"events_partitioned is missing in Bronze. Build it once: {EVENTS_BOOTSTRAP_COMMAND}"
        )
    by_table: dict[str, int] = {}
    for table in csv_tables.CSV_TABLES:
        rows = load_day(table, data_date)
        log.info("%s: %s rows", table, rows)
        # 0 rows means no Raw file for this day. That is a failure, never a quiet "success":
        # Silver and Gold would run on old data and the freshness check would still be green.
        if rows == 0:
            raise RuntimeError(
                f"bronze {table}: no Raw file for {data_date}. "
                "Did the ingest step run for this date?"
            )
        by_table[table] = rows
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_silver(data_date: str) -> StepOutcome:
    # On purpose, data_date is not passed to dbt. Silver rebuilds from ALL of Bronze: it keeps the
    # newest row of each id. The date is only recorded in pipeline_runs for this run.
    return StepOutcome(detail=run_dbt("silver"))


def step_gold(data_date: str) -> StepOutcome:
    # Same as Silver: Gold is rebuilt as a whole (the business rules live here), so it does not
    # use the date either.
    return StepOutcome(detail=run_dbt("gold"))


# A step takes the data date and returns a StepOutcome.
STEPS = [
    ("ingest", step_ingest),
    ("bronze", step_bronze),
    ("silver", step_silver),
    ("gold", step_gold),
]


def run_step(
    run_id: str,
    name: str,
    func: Callable[[str], StepOutcome],
    data_date: str,
) -> None:
    """Run one step and record it in pipeline_runs. Re-raise the error so the run stops."""
    started = datetime.now(UTC)
    # The status is "failed" until the step returns. Anything that stops it early (an error,
    # SystemExit, Ctrl+C) is then recorded as failed, never as success.
    status, rows, detail, error = "failed", None, None, None
    interrupted = False
    log.info("[run %s] step %s starts for %s", run_id, name, data_date)
    try:
        outcome = func(data_date)
        rows, detail = outcome.rows, outcome.detail
        status = "success"
    except KeyboardInterrupt:
        # Ctrl+C: leave fast. No network calls here (BigQuery) that could hang the
        # shutdown, so this run is not recorded.
        interrupted = True
        error = "interrupted: KeyboardInterrupt"
        log.error("[run %s] step %s was interrupted", run_id, name)
        raise
    except (Exception, SystemExit) as exc:
        error = (str(exc) or type(exc).__name__)[:MAX_ERROR_CHARS]
        log.exception("[run %s] step %s FAILED: %s", run_id, name, error)
        raise
    finally:
        finished = datetime.now(UTC)
        if not interrupted:
            row = run_row(run_id, name, data_date, status, started, finished, rows, error, detail)
            record_run(row)
    log.info("[run %s] step %s done in %.1fs", run_id, name, (finished - started).total_seconds())


def run_steps(
    data_date: str,
    first_step: str,
    last_step: str,
    run_id: str | None = None,
) -> None:
    """Run the steps from first_step to last_step (both included) for one data date.

    All steps share one run_id, so pipeline_runs can group them. Airflow runs one step per task,
    so it passes its own run id; by hand, a new id is made.
    """
    data_date = valid_date(data_date)  # stop a wrong date before any step runs
    names = [name for name, _ in STEPS]
    run_id = run_id or new_id()
    for name, func in STEPS[names.index(first_step) : names.index(last_step) + 1]:
        run_step(run_id, name, func, data_date)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, type=date_arg, help="YYYY-MM-DD")
    names = [name for name, _ in STEPS]
    parser.add_argument("--from-step", choices=names)
    parser.add_argument("--to-step", choices=names)
    parser.add_argument("--run-id", help="share one id between steps (Airflow passes its run id)")
    args = parser.parse_args()

    from_step, to_step = args.from_step or names[0], args.to_step or names[-1]
    if names.index(from_step) > names.index(to_step):
        parser.error("--from-step must come before --to-step")

    setup_cli_logging(PIPELINE_FORMAT)
    run_steps(args.date, from_step, to_step, run_id=args.run_id)


if __name__ == "__main__":
    main()
