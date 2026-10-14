"""Load the course CSV tables into the Raw Zone (full load).

The four small CSV files were loaded once into the BigQuery dataset `stylehub` by
storage/setup/load_csv.py. This step reads each table from there, checks the columns, and writes a
Parquet file to the Raw Zone with the three metadata columns.

The CSV files have no updated_at column, so there is no watermark. Every run is a full load.
Re-running adds a new file (append-only). Bronze loads only the latest file of each day,
and Silver keeps the latest row of each id.

Usage: python -m ingestion.csv_tables --table orders --date 2026-10-01 [--dry-run]
"""

import argparse
import time

from google.cloud import bigquery

from common.config import load_env, settings
from common.retry import call_with_retry
from ingestion.raw_writer import write_raw
from ingestion.schema_check import ON_CHANGE_CHOICES, OnChange, enforce_schema

CSV_TABLES = ("orders", "order_items", "products", "users")
SOURCE_NAME = "csv"
# Columns that Parquet cannot hold well (map/geography text is fine, but keep Raw simple).
DROP_COLUMNS = {"users": ["user_geom"]}


def extract_full(table: str):
    """Every row of one CSV table, read from the BigQuery dataset with the CSV data."""
    if table not in CSV_TABLES:
        raise ValueError(f"No CSV table configured: {table}")
    cfg = settings()
    client = bigquery.Client(project=cfg.project)
    query = f"SELECT * FROM `{cfg.project}.{cfg.source}.{table}`"
    df = call_with_retry(lambda: client.query(query).to_dataframe())
    return df.drop(columns=DROP_COLUMNS.get(table, []), errors="ignore")


def ingest_table(
    table: str,
    data_date: str,
    dry_run: bool = False,
    on_schema_change: OnChange = "fail",
) -> str:
    """Extract one CSV table. With dry_run, only count the rows and write nothing to GCS."""
    load_env()
    started = time.perf_counter()
    df = enforce_schema(extract_full(table), table, on_schema_change)

    if dry_run:
        seconds = time.perf_counter() - started
        note = f"csv, {seconds:.1f}s, dry run, nothing written"
        return f"{table} {data_date}: {len(df)} rows ({note})"
    uri = write_raw(df, table, data_date, source=SOURCE_NAME)
    seconds = time.perf_counter() - started
    return f"{table} {data_date}: {len(df)} rows (csv, {seconds:.1f}s) -> {uri}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, choices=CSV_TABLES)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--on-schema-change", choices=ON_CHANGE_CHOICES, default="fail")
    args = parser.parse_args()
    print(ingest_table(args.table, args.date, args.dry_run, args.on_schema_change))


if __name__ == "__main__":
    main()
