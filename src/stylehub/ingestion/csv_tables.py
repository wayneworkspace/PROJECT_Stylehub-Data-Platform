"""Load the course CSV tables into the Raw Zone (full load).

Reads each table from the BigQuery dataset `stylehub`, checks the columns, and writes a Parquet
file to the Raw Zone with the three metadata columns. There is no updated_at column, so there is
no watermark: every run is a full load, and a re-run adds a new file (append-only).
--date is only the LABEL of the Raw folder: a label older than a few days holds today's data.

Usage: python -m stylehub.ingestion.csv_tables --table orders --date 2026-10-01 [--dry-run]
"""

import argparse
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pandas as pd
from google.cloud import bigquery

from stylehub.common.bq import query_config
from stylehub.common.clients import bq_client
from stylehub.common.config import Settings, load_env, resolve
from stylehub.common.dates import backfill_dates, date_arg, valid_date, watermark_window
from stylehub.common.logs import setup_cli_logging
from stylehub.common.retry import call_with_retry
from stylehub.ingestion.raw_writer import write_raw
from stylehub.ingestion.schema_check import (
    add_missing_columns,
    check_declared_schema,
    type_empty_columns,
)

log = logging.getLogger(__name__)

CSV_TABLES = ("orders", "order_items", "products", "users")
SOURCE_NAME = "csv"
# user_geom is a GEOGRAPHY column. Raw stays plain Parquet, so it is not copied.
DROP_COLUMNS = {"users": ["user_geom"]}
# Incremental tables (session 2). The course tables have no updated_at, so the time of the last
# change is the latest of the order dates: a status change sets shipped_at, delivered_at or
# returned_at. products and users are small and are always loaded in full.
LAST_CHANGE = (
    "GREATEST(created_at, IFNULL(shipped_at, created_at),"
    " IFNULL(delivered_at, created_at), IFNULL(returned_at, created_at))"
)
CHANGED_AT = {"orders": LAST_CHANGE, "order_items": LAST_CHANGE}
# A label older than this many days holds today's data under an old name (see the docstring).
MAX_LABEL_AGE_DAYS = 3


class SourceRowMismatch(RuntimeError):
    """The rows read are not the rows the source table says it has."""


@dataclass(frozen=True)
class IngestResult:
    """What one ingestion did. str(result) is the sentence for the log."""

    table: str
    data_date: str
    rows: int
    seconds: float
    uri: str | None = None  # None in a dry run: nothing was written

    def __str__(self) -> str:
        head = f"{self.table} {self.data_date}: {self.rows} rows"
        if self.uri is None:
            return f"{head} ({self.seconds:.1f}s, dry run, nothing written)"
        return f"{head} ({self.seconds:.1f}s) -> {self.uri}"


def warn_if_backdated(data_date: str, today: date | None = None) -> bool:
    """Log a warning and return True when data_date is older than MAX_LABEL_AGE_DAYS."""
    today = today or datetime.now(UTC).date()
    age_days = (today - date.fromisoformat(data_date)).days
    if age_days <= MAX_LABEL_AGE_DAYS:
        return False
    log.warning(
        "data_date %s is %d days old, but the source is read as it is TODAY. The Raw folder "
        "date=%s will hold today's data, not the data of that day.",
        data_date,
        age_days,
        data_date,
    )
    return True


def extract_full(
    table: str,
    client: bigquery.Client | None = None,
    cfg: Settings | None = None,
    data_date: str | None = None,
    on_schema_change: str = "fail",
) -> pd.DataFrame:
    """Rows of one CSV table, read from the BigQuery dataset with the CSV data.

    Without data_date: every row (full load). With data_date: only the rows that changed from
    LOOKBACK_DAYS before that day to that day (incremental load, see CHANGED_AT).
    Checks the declared columns first (nothing is read if they are wrong), and for a full load
    the row count after the read.
    """
    if table not in CSV_TABLES:
        raise ValueError(f"No CSV table configured: {table}")
    cfg = resolve(cfg)
    if client is None:
        client = bq_client(cfg)
    table_id = f"{cfg.project}.{cfg.source}.{table}"
    source = call_with_retry(lambda: client.get_table(table_id))
    dropped = DROP_COLUMNS.get(table, [])
    check_declared_schema(
        table, [f for f in source.schema if f.name not in dropped], on_schema_change
    )
    where = ""
    if data_date is not None:
        if table not in CHANGED_AT:
            raise ValueError(f"{table} has no change time, so it is loaded in full")
        first, last = watermark_window(data_date)  # also checks the date, so the SQL is safe
        where = f" WHERE DATE({CHANGED_AT[table]}) BETWEEN '{first}' AND '{last}'"
    # The table name is checked against CSV_TABLES above, the dataset comes from our settings.
    query = f"SELECT * FROM `{table_id}`{where}"  # noqa: S608
    df = call_with_retry(lambda: client.query(query, job_config=query_config(cfg)).to_dataframe())
    if not where and source.num_rows is not None and len(df) != source.num_rows:
        raise SourceRowMismatch(f"{table}: read {len(df)} rows, the source has {source.num_rows}")
    df = add_missing_columns(df.drop(columns=dropped, errors="ignore"), table)
    return type_empty_columns(df, table)


def ingest_table(
    table: str,
    data_date: str,
    dry_run: bool = False,
    incremental: bool = False,
    on_schema_change: str = "fail",
) -> IngestResult:
    """Extract one CSV table. With dry_run, only count the rows and write nothing to GCS.

    incremental=True reads only the changed rows and writes them to the Raw folder
    `<table>_incremental`. Bronze does not load that folder: Bronze keeps one FULL snapshot per
    day and Silver reads only the newest one, so a partial file there would drop rows.
    """
    valid_date(data_date)  # before anything is read or written
    warn_if_backdated(data_date)
    load_env()
    started = time.perf_counter()
    df = extract_full(
        table, data_date=data_date if incremental else None, on_schema_change=on_schema_change
    )
    raw_table = f"{table}_incremental" if incremental else table
    uri = None if dry_run else write_raw(df, raw_table, data_date, source=SOURCE_NAME)
    return IngestResult(raw_table, data_date, len(df), time.perf_counter() - started, uri)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, choices=CSV_TABLES)
    parser.add_argument("--date", required=True, type=date_arg, help="YYYY-MM-DD")
    parser.add_argument("--backfill-days", type=int, default=1, help="load the last N days")
    parser.add_argument("--incremental", action="store_true", help="read only the changed rows")
    parser.add_argument("--on-schema-change", choices=("fail", "absorb"), default="fail")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    setup_cli_logging()
    for data_date in backfill_dates(args.date, args.backfill_days):
        result = ingest_table(
            args.table, data_date, args.dry_run, args.incremental, args.on_schema_change
        )
        log.info("%s", result)


if __name__ == "__main__":
    main()
