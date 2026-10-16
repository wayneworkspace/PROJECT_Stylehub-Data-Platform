"""Load the course CSV tables into the Raw Zone (full load).

The four small CSV files were loaded once into the BigQuery dataset `stylehub` by
setup/load_csv.py. This step reads each table from there, checks the columns, and writes a
Parquet file to the Raw Zone with the three metadata columns.

The CSV files have no updated_at column, so there is no watermark. Every run is a full load.
Re-running adds a new file (append-only). Bronze loads only the latest file of each day,
and Silver keeps the latest row of each id.

--date is only the LABEL of the Raw folder. The source is read as it is now, so a label older than
a few days holds today's data under an old name (the run logs a warning).

Before the data is read, the declared columns of the source table are checked (metadata only),
and after it is read the number of rows is compared with the table's row count.

Usage: python -m stylehub.ingestion.csv_tables --table orders --date 2026-10-01 [--dry-run]
"""

import argparse
import logging

import pandas as pd
from google.cloud import bigquery

from stylehub.common.bq import query_config
from stylehub.common.config import Settings, resolve
from stylehub.common.dates import date_arg
from stylehub.common.logs import setup_cli_logging
from stylehub.common.retry import call_with_retry
from stylehub.ingestion.runner import IngestResult, run_ingest
from stylehub.ingestion.schema_check import ON_CHANGE_CHOICES, OnChange, check_declared_schema

log = logging.getLogger(__name__)

CSV_TABLES = ("orders", "order_items", "products", "users")
SOURCE_NAME = "csv"
# Columns that Parquet cannot hold well (map/geography text is fine, but keep Raw simple).
DROP_COLUMNS = {"users": ["user_geom"]}


class SourceRowMismatch(RuntimeError):
    """The rows read are not the rows the source table says it has."""


def extract_full(
    table: str,
    client: bigquery.Client | None = None,
    on_schema_change: OnChange = "fail",
    cfg: Settings | None = None,
) -> pd.DataFrame:
    """Every row of one CSV table, read from the BigQuery dataset with the CSV data.

    Checks the declared columns first (nothing is read if they are wrong), and the row count
    after the read.
    """
    if table not in CSV_TABLES:
        raise ValueError(f"No CSV table configured: {table}")
    cfg = resolve(cfg)
    if client is None:
        client = bigquery.Client(project=cfg.project)
    table_id = f"{cfg.project}.{cfg.source}.{table}"
    source = call_with_retry(lambda: client.get_table(table_id))
    dropped = DROP_COLUMNS.get(table, [])
    check_declared_schema(
        table, [f for f in source.schema if f.name not in dropped], on_schema_change
    )
    # The table name is checked against CSV_TABLES above, the dataset comes from our settings.
    query = f"SELECT * FROM `{table_id}`"  # noqa: S608
    df = call_with_retry(lambda: client.query(query, job_config=query_config(cfg)).to_dataframe())
    if source.num_rows is not None and len(df) != source.num_rows:
        raise SourceRowMismatch(f"{table}: read {len(df)} rows, the source has {source.num_rows}")
    return df.drop(columns=dropped, errors="ignore")


def ingest_table(
    table: str,
    data_date: str,
    dry_run: bool = False,
    on_schema_change: OnChange = "fail",
) -> IngestResult:
    """Extract one CSV table. With dry_run, only count the rows and write nothing to GCS."""
    return run_ingest(
        table,
        data_date,
        lambda: extract_full(table, on_schema_change=on_schema_change),
        source=SOURCE_NAME,
        mode="csv",
        dry_run=dry_run,
        on_schema_change=on_schema_change,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, choices=CSV_TABLES)
    parser.add_argument("--date", required=True, type=date_arg, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--on-schema-change", choices=ON_CHANGE_CHOICES, default="fail")
    args = parser.parse_args()
    setup_cli_logging()
    log.info("%s", ingest_table(args.table, args.date, args.dry_run, args.on_schema_change))


if __name__ == "__main__":
    main()
