"""Load one table from Postgres into the Raw Zone (session 2).

Only extracts and writes raw data. Two modes:
- incremental (default): rows whose watermark column falls in the window of the data date.
  The window starts one lookback earlier, to catch late-arriving rows.
- full load (--full-load): the whole table. Use it for the first load or a small table.
  The file is stored under the data date you pass.

Re-running only creates new files (append-only). Bronze keeps everything and Silver drops
the duplicates. Before writing, the columns are compared with the expected schema
(src/python/ingestion/schema_check.py), so a source that changes its columns is noticed early.

The watermark column of order_items must be chosen from real data: check whether
updated_at of order_items changes when an order changes status (see docs/DECISIONS.md, section 2).

Usage: python -m ingestion.incremental --table orders --date 2026-10-01
           [--full-load] [--dry-run] [--on-schema-change absorb]
"""

import argparse
import os
import time
from contextlib import closing
from datetime import date, datetime, timedelta

import pandas as pd
import psycopg2

from ingestion.raw_writer import write_raw
from ingestion.schema_check import ON_CHANGE_CHOICES, OnChange, enforce_schema
from pipeline.config import load_env

# table -> watermark column. Add new tables here, do not change the logic below.
WATERMARK = {
    "orders": "updated_at",
    "order_items": "updated_at",
}
INCREMENTAL_TABLES = tuple(WATERMARK)
LOOKBACK_DAYS = 1


def window_for(data_date: date, lookback_days: int = LOOKBACK_DAYS) -> tuple[datetime, datetime]:
    """The [start, end) range to read for one data date."""
    start = datetime.combine(data_date - timedelta(days=lookback_days), datetime.min.time())
    end = datetime.combine(data_date + timedelta(days=1), datetime.min.time())
    return start, end


def connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ["PG_DATABASE"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
    )


def _fetch(query: str, params: tuple = ()) -> pd.DataFrame:
    """Run one query and return the rows as a DataFrame."""
    # closing() really closes the connection. psycopg2's own "with" only ends the transaction.
    with closing(connect()) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        columns = [col.name for col in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)


def _check_known(table: str) -> None:
    # Table and column names cannot be query parameters. They are safe in the queries below
    # because they come from the WATERMARK dict, never from user input.
    if table not in WATERMARK:
        raise ValueError(f"No watermark configured for table: {table}")


def extract_day(table: str, data_date: date) -> pd.DataFrame:
    """Incremental: the rows changed in the window of one data date."""
    _check_known(table)
    column = WATERMARK[table]
    start, end = window_for(data_date)
    query = f"SELECT * FROM {table} WHERE {column} >= %s AND {column} < %s"
    return _fetch(query, (start, end))


def extract_full(table: str) -> pd.DataFrame:
    """Full load: every row of the table."""
    _check_known(table)
    return _fetch(f"SELECT * FROM {table}")


def ingest_table(
    table: str,
    data_date: str,
    dry_run: bool = False,
    full_load: bool = False,
    on_schema_change: OnChange = "fail",
) -> str:
    """Extract one table. With dry_run, only count the rows and write nothing to GCS."""
    load_env()
    started = time.perf_counter()
    if full_load:
        df = extract_full(table)
    else:
        df = extract_day(table, date.fromisoformat(data_date))
    df = enforce_schema(df, table, on_schema_change)

    mode = "full load" if full_load else "incremental"
    if dry_run:
        seconds = time.perf_counter() - started
        note = f"{mode}, {seconds:.1f}s, dry run, nothing written"
        return f"{table} {data_date}: {len(df)} rows ({note})"
    uri = write_raw(df, table, data_date, source="postgres")
    seconds = time.perf_counter() - started
    return f"{table} {data_date}: {len(df)} rows ({mode}, {seconds:.1f}s) -> {uri}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, choices=INCREMENTAL_TABLES)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--full-load", action="store_true", help="read the whole table, not only one day"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="read from Postgres but do not write to GCS"
    )
    parser.add_argument(
        "--on-schema-change",
        choices=ON_CHANGE_CHOICES,
        default="fail",
        help="fail: stop when columns are missing or retyped. absorb: fill NULL and go on",
    )
    args = parser.parse_args()
    print(
        ingest_table(
            args.table,
            args.date,
            dry_run=args.dry_run,
            full_load=args.full_load,
            on_schema_change=args.on_schema_change,
        )
    )


if __name__ == "__main__":
    main()
