"""Load the Raw files of one day into Bronze. Append only, never overwrite.

Re-running the same day adds duplicate rows to Bronze. That is intentional: Bronze keeps every
ingest and Silver removes the duplicates.

Usage: python -m storage.load_bronze --date 2026-10-01 [--table orders]
"""

import argparse

from google.cloud import bigquery

from common.config import RAW_DIR, settings

TABLES = ("orders", "order_items", "products", "users", "shipments")


def load_day(table: str, data_date: str) -> int:
    """Append the Raw files of one table and one day to Bronze. Return the rows loaded."""
    cfg = settings()
    raw_dir = RAW_DIR.get(table, table)
    uri = f"gs://{cfg.bucket}/{cfg.raw_prefix}/{raw_dir}/date={data_date}/*"
    table_id = f"{cfg.project}.{cfg.bronze}.{table}"

    client = bigquery.Client(project=cfg.project)
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_uri(uri, table_id, job_config=config)
    job.result()
    return job.output_rows or 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--table", choices=TABLES)
    args = parser.parse_args()

    for table in [args.table] if args.table else TABLES:
        print(f"{table} {args.date}: {load_day(table, args.date)} rows -> Bronze")


if __name__ == "__main__":
    main()
