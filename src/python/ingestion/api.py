"""Load one day of an API table into the Raw Zone (session 2).

Same job as ingestion/database.py, for a REST API: only extract and write raw data.
The API returns the rows created in a date range. We ask for one day, so the Raw files stay
organized by date. Re-running a day adds a new file (append-only), Silver drops the duplicates.

Before the first real run, check the API Reference: is created_to included in the range?
If it is not, change day_params() so it asks for the next day as the end.

Usage: python -m ingestion.api --table users --date 2026-10-01 [--dry-run]
"""

import argparse
import time
from datetime import date

import pandas as pd

from common.config import load_env
from ingestion.raw_writer import write_raw
from ingestion.schema_check import ON_CHANGE_CHOICES, OnChange, enforce_schema
from sources.stylehub_api import fetch_rows

# table -> API endpoint. Add new API tables here, do not change the logic below.
ENDPOINTS = {"users": "stylehub-users"}
API_TABLES = tuple(ENDPOINTS)
SOURCE_NAME = "stylehub_api"


def day_params(data_date: date) -> dict[str, str]:
    """Query parameters that ask for the rows created on one day."""
    day = data_date.isoformat()
    return {"created_from": day, "created_to": day}


def extract_day(table: str, data_date: date) -> pd.DataFrame:
    """Read every page of one day. Return the rows as a DataFrame."""
    if table not in ENDPOINTS:
        raise ValueError(f"No API endpoint configured for table: {table}")
    return pd.DataFrame(fetch_rows(ENDPOINTS[table], day_params(data_date)))


def ingest_table(
    table: str,
    data_date: str,
    dry_run: bool = False,
    on_schema_change: OnChange = "fail",
) -> str:
    """Extract one API table. With dry_run, only count the rows and write nothing to GCS."""
    load_env()
    started = time.perf_counter()
    df = extract_day(table, date.fromisoformat(data_date))
    df = enforce_schema(df, table, on_schema_change)

    if dry_run:
        seconds = time.perf_counter() - started
        note = f"api, {seconds:.1f}s, dry run, nothing written"
        return f"{table} {data_date}: {len(df)} rows ({note})"
    uri = write_raw(df, table, data_date, source=SOURCE_NAME)
    seconds = time.perf_counter() - started
    return f"{table} {data_date}: {len(df)} rows (api, {seconds:.1f}s) -> {uri}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, choices=API_TABLES)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--dry-run", action="store_true", help="read the API but do not write to GCS"
    )
    parser.add_argument(
        "--on-schema-change",
        choices=ON_CHANGE_CHOICES,
        default="fail",
        help="fail: stop when columns are missing or retyped. absorb: fill NULL and go on",
    )
    args = parser.parse_args()
    print(ingest_table(args.table, args.date, args.dry_run, args.on_schema_change))


if __name__ == "__main__":
    main()
