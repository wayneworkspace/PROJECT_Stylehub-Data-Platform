"""Run one pipeline step for one date; record it in pipeline_runs."""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from importlib import import_module
from typing import Any

get_logger = import_module("src.0_utils.logger").get_logger

config = import_module("src.1_source.config")
utils = import_module("src.1_source.utils")
api_users = import_module("src.2_ingestion.api_users")
csv_tables = import_module("src.2_ingestion.csv_tables")
pg_tables = import_module("src.2_ingestion.postgres_tables")
events_bronze = import_module("src.3_storage.events_bronze")
load_bronze = import_module("src.3_storage.load_bronze")
reconcile = import_module("src.3_storage.reconcile")
runs = import_module("src.3_storage.runs")
run_dbt = import_module("src.4_transform.run_dbt")

log = get_logger("pipeline")

MAX_ERROR_CHARS = 500  # cut long errors so pipeline_runs rows stay small


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """Step result; rows and detail are saved in pipeline_runs."""

    rows: int | None = None
    detail: dict[str, Any] | None = None


def step_ingest(data_date: str, cfg: config.Settings) -> StepOutcome:
    # Full load of every CSV table into the Raw Zone.
    by_table = {t: csv_tables.ingest_table(t, data_date, cfg) for t in csv_tables.CSV_TABLES}
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_bronze(data_date: str, cfg: config.Settings) -> StepOutcome:
    # events is built once by setup; fail early if missing.
    if not events_bronze.events_table_exists(cfg):
        raise RuntimeError(
            "events_partitioned is missing in Bronze. "
            "Build it once: uv run python -m src.3_storage.events_bronze"
        )
    by_table: dict[str, int] = {}
    for table in csv_tables.CSV_TABLES:
        rows = load_bronze.load_day(table, data_date, cfg)
        log.info("%s: %s rows", table, rows)
        # No Raw file is a failure, never a quiet success.
        if rows == 0:
            raise RuntimeError(
                f"bronze {table}: no Raw file for {data_date}. "
                "Did the ingest step run for this date?"
            )
        by_table[table] = rows
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_pg_ingest(data_date: str, cfg: config.Settings) -> StepOutcome:
    # Incremental load of the Postgres tables, watermark updated_at.
    by_table = {t: pg_tables.ingest_table(t, data_date, cfg) for t in pg_tables.PG_TABLES}
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_pg_bronze(data_date: str, cfg: config.Settings) -> StepOutcome:
    # No Raw file means no changed rows that day; partitions never expire.
    by_table = {
        t: load_bronze.load_day(pg_tables.raw_name(t), data_date, cfg, keep_days=None)
        for t in pg_tables.PG_TABLES
    }
    log.info("pg bronze rows: %s", by_table)
    return StepOutcome(sum(by_table.values()), {"rows_by_table": by_table})


def step_pg_reconcile(data_date: str, cfg: config.Settings) -> StepOutcome:
    # Full id compare each day; Silver flags the deleted ids is_deleted.
    counts = reconcile.reconcile(cfg)
    return StepOutcome(sum(counts.values()), {"deleted_by_table": counts})


def step_api_ingest(data_date: str, cfg: config.Settings) -> StepOutcome:
    # Incremental load of the API users, watermark updated_at.
    rows = api_users.ingest(data_date, cfg)
    return StepOutcome(rows, {"rows_by_table": {api_users.TABLE: rows}})


def step_api_bronze(data_date: str, cfg: config.Settings) -> StepOutcome:
    # No Raw file means no changed users that day; partitions never expire.
    rows = load_bronze.load_day(api_users.TABLE, data_date, cfg, keep_days=None)
    return StepOutcome(rows, {"rows_by_table": {api_users.TABLE: rows}})


def step_dbt(layer: str, data_date: str, cfg: config.Settings) -> StepOutcome:
    # dbt rebuilds the whole layer, so the date is not used.
    return StepOutcome(detail=run_dbt.run_dbt(layer))


# Each step takes (data_date, cfg) and returns a StepOutcome.
STEPS = {
    "ingest": step_ingest,
    "bronze": step_bronze,
    "silver": partial(step_dbt, "silver"),
    "gold": partial(step_dbt, "gold"),
    "pg_ingest": step_pg_ingest,
    "pg_bronze": step_pg_bronze,
    "pg_reconcile": step_pg_reconcile,
    "pg_silver": partial(step_dbt, "pg_silver"),
    "pg_gold": partial(step_dbt, "pg_gold"),
    "api_ingest": step_api_ingest,
    "api_bronze": step_api_bronze,
    "api_silver": partial(step_dbt, "api_silver"),
}


def run_step(data_date: str, step: str, run_id: str) -> None:
    """Run one step, record it in pipeline_runs, re-raise any error."""
    data_date = utils.valid_date(data_date)  # stop a wrong date before the step runs
    cfg = config.settings()
    started = datetime.now(UTC)
    # Status stays failed unless the step returns normally.
    status, rows, detail, error = "failed", None, None, None
    log.info("[run %s] step %s starts for %s", run_id, step, data_date)
    try:
        outcome = STEPS[step](data_date, cfg)
        rows, detail = outcome.rows, outcome.detail
        status = "success"
    except Exception as exc:
        error = (str(exc) or type(exc).__name__)[:MAX_ERROR_CHARS]
        log.exception("[run %s] step %s FAILED: %s", run_id, step, error)
        raise
    finally:
        finished = datetime.now(UTC)
        runs.record_run(
            run_id, step, data_date, status, started, finished, rows, error, detail, cfg
        )
    log.info("[run %s] step %s done in %.1fs", run_id, step, (finished - started).total_seconds())


def main(argv: list[str] | None = None) -> None:
    """Command line for the scheduled GitHub workflow: DATA_DATE STEP RUN_ID."""
    data_date, step, run_id = sys.argv[1:] if argv is None else argv
    run_step(data_date, step, run_id)


if __name__ == "__main__":
    main()
