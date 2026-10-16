"""Run the whole pipeline for one date, step by step. Each step is its own function.

Airflow runs the same steps, one task per step (see deploy/airflow/dags/stylehub_daily.py).
Silver and Gold are built by dbt, which also runs the tests, so there is no separate checks step.

Every step is logged, recorded in BigQuery (pipeline_runs) and sends an alert if it fails.

Usage:
    python -m stylehub.orchestration.run_daily --date 2026-10-01 \
        [--from-step bronze] [--to-step gold]
"""

import argparse
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from stylehub.bronze.events_bronze import EVENTS_BOOTSTRAP_COMMAND, events_table_exists
from stylehub.bronze.load_bronze import TABLES, load_day
from stylehub.common.dates import date_arg, valid_date
from stylehub.common.ids import new_id
from stylehub.ingestion import csv_tables
from stylehub.orchestration.alerts import send_alert
from stylehub.orchestration.runs import record_run, run_row, save_pending
from stylehub.transform.run_dbt import run_dbt

log = logging.getLogger("pipeline")

MAX_ERROR_CHARS = 500  # Longer errors are cut, so one pipeline_runs row stays small.


@dataclass(frozen=True)
class StepOutcome:
    """What a step returns when it has more to say than a row count.

    rows goes to pipeline_runs.rows_loaded. detail (rows per table, dbt test counts, ...) goes to
    pipeline_runs.detail as JSON. A step may still return a plain int or None.
    """

    rows: int | None = None
    detail: dict[str, Any] | None = None


StepResult = int | StepOutcome | None


def as_outcome(result: StepResult) -> StepOutcome:
    return result if isinstance(result, StepOutcome) else StepOutcome(rows=result)


def step_ingest(data_date: str) -> StepResult:
    # The course data comes from CSV files: full load, no watermark.
    # The old Postgres and API sources were removed from the package.
    by_table: dict[str, int] = {}
    for table in csv_tables.CSV_TABLES:
        result = csv_tables.ingest_table(table, data_date)
        log.info("%s", result)
        by_table[table] = result.rows
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_bronze(data_date: str) -> StepResult:
    # events is a one-time build (15 GB copy), so it is NOT part of the daily run. If it is
    # missing, stop here with a clear message instead of letting Silver fail later.
    if not events_table_exists():
        raise RuntimeError(
            f"events_partitioned is missing in Bronze. Build it once: {EVENTS_BOOTSTRAP_COMMAND}"
        )
    by_table: dict[str, int] = {}
    for table in TABLES:
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


def step_silver(data_date: str) -> StepResult:
    # On purpose, data_date is not passed to dbt. Silver rebuilds from ALL of Bronze: it keeps the
    # newest row of each id. The date is only recorded in pipeline_runs for this run.
    return StepOutcome(detail=run_dbt("silver"))


def step_gold(data_date: str) -> StepResult:
    # Same as Silver: Gold is rebuilt as a whole (the business rules live here), so it does not
    # use the date either.
    return StepOutcome(detail=run_dbt("gold"))


# A step takes the data date and returns a StepOutcome, a row count, or None.
STEPS = [
    ("ingest", step_ingest),
    ("bronze", step_bronze),
    ("silver", step_silver),
    ("gold", step_gold),
]


def run_step(
    run_id: str,
    name: str,
    func: Callable[[str], StepResult],
    data_date: str,
    alert: bool = True,
) -> None:
    """Run one step. Record it and alert on failure. Re-raise the error so the run stops.

    alert=False is for Airflow: the DAG sends one alert itself when a task fails for good
    (on_failure_callback), so a retry does not send a second message. The run is recorded anyway.
    """
    started = datetime.now(UTC)
    # The status is "failed" until the step returns. Anything that stops it early (an error,
    # SystemExit, Ctrl+C) is then recorded as failed, never as success.
    status, rows, detail, error = "failed", None, None, None
    interrupted = False
    log.info("[run %s] step %s starts for %s", run_id, name, data_date)
    try:
        outcome = as_outcome(func(data_date))
        rows, detail = outcome.rows, outcome.detail
        status = "success"
    except KeyboardInterrupt:
        # Ctrl+C: leave fast. No network calls here (BigQuery, webhook) that could hang the
        # shutdown. The row is kept in the local pending file and goes out with the next run.
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
        row = run_row(run_id, name, data_date, status, started, finished, rows, error, detail)
        if interrupted:
            save_pending(row)
        else:
            record_run(row)
            if status == "failed" and alert:
                send_alert(
                    f"StyleHub pipeline FAILED\nstep: {name}\ndate: {data_date}\n"
                    f"run: {run_id}\nerror: {error}"
                )
    log.info("[run %s] step %s done in %.1fs", run_id, name, (finished - started).total_seconds())


def run_steps(
    data_date: str,
    first_step: str,
    last_step: str,
    run_id: str | None = None,
    alert: bool = True,
) -> None:
    """Run the steps from first_step to last_step (both included) for one data date.

    All steps share one run_id, so pipeline_runs can group them. Airflow runs one step per task,
    so it passes its own run id; by hand, a new id is made.
    """
    data_date = valid_date(data_date)  # stop a wrong date before any step runs
    names = [name for name, _ in STEPS]
    run_id = run_id or new_id()
    for name, func in STEPS[names.index(first_step) : names.index(last_step) + 1]:
        run_step(run_id, name, func, data_date, alert=alert)


def setup_logging() -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, type=date_arg, help="YYYY-MM-DD")
    parser.add_argument("--from-step")
    parser.add_argument("--to-step")
    parser.add_argument("--run-id", help="share one id between steps (Airflow passes its run id)")
    parser.add_argument(
        "--no-alert",
        action="store_true",
        help="do not send the failure alert (Airflow sends it itself, once, after the retries)",
    )
    args = parser.parse_args()

    names = [name for name, _ in STEPS]
    from_step, to_step = args.from_step or names[0], args.to_step or names[-1]
    for step in (from_step, to_step):
        if step not in names:
            parser.error(f"step '{step}' does not exist: {names}")
    if names.index(from_step) > names.index(to_step):
        parser.error("--from-step must come before --to-step")

    setup_logging()
    run_steps(args.date, from_step, to_step, run_id=args.run_id, alert=not args.no_alert)


if __name__ == "__main__":
    main()
