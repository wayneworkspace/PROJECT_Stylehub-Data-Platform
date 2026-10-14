"""Load the Raw files of one day into Bronze. Safe to re-run.

Each ingest writes a new batch under the day's Raw folder. Bronze keeps only the LATEST batch of
each day, so running a day twice does not double the rows. Different days stay side by side, so
Bronze still holds one snapshot per day and Silver picks the newest row of each id.

The order is: load the new batch first, delete the older batches after. If the load fails, the old
rows are still there, so Bronze never loses a day. If the delete fails, the day has two batches
for a while. That is harmless (Silver keeps the newest row) and the next run removes the old one.

Usage: python -m storage.load_bronze --date 2026-10-01 [--table orders]
"""

import argparse

from google.api_core.exceptions import NotFound
from google.cloud import bigquery, storage

from common.config import RAW_DIR, settings
from common.retry import call_with_retry

TABLES = ("orders", "order_items", "products", "users")


def batch_ids_from_names(names: list[str]) -> list[str]:
    """The batch ids found in Raw file names, oldest first (ids start with a timestamp)."""
    ids = set()
    for name in names:
        for part in name.split("/"):
            if part.startswith("batch_id="):
                ids.add(part.removeprefix("batch_id="))
    return sorted(ids)


def list_batch_ids(prefix: str) -> list[str]:
    """The batch ids of one table and one day, read from the Raw Zone on GCS."""
    cfg = settings()
    blobs = storage.Client(project=cfg.project).list_blobs(cfg.bucket, prefix=prefix)
    return batch_ids_from_names([blob.name for blob in blobs])


def table_exists(client: bigquery.Client, table_id: str) -> bool:
    try:
        client.get_table(table_id)
    except NotFound:
        return False
    return True


def count_batch_rows(client: bigquery.Client, table_id: str, batch_id: str) -> int:
    """How many rows of a batch are already in Bronze."""
    query = f"SELECT COUNT(*) AS n FROM `{table_id}` WHERE _batch_id = @batch_id"
    params = [bigquery.ScalarQueryParameter("batch_id", "STRING", batch_id)]
    config = bigquery.QueryJobConfig(query_parameters=params)
    rows = call_with_retry(lambda: client.query(query, job_config=config).result())
    return next(iter(rows)).n


def delete_batches(client: bigquery.Client, table_id: str, batch_ids: list[str]) -> None:
    """Remove the rows of older batches of the same day."""
    query = f"DELETE FROM `{table_id}` WHERE _batch_id IN UNNEST(@batch_ids)"
    params = [bigquery.ArrayQueryParameter("batch_ids", "STRING", batch_ids)]
    config = bigquery.QueryJobConfig(query_parameters=params)
    call_with_retry(lambda: client.query(query, job_config=config).result())


def load_day(table: str, data_date: str) -> int:
    """Make Bronze hold the latest Raw batch of one table and one day. Return the rows loaded.

    Returns 0 when nothing was loaded: no Raw file, or the latest batch is already in Bronze.
    """
    cfg = settings()
    raw_dir = RAW_DIR.get(table, table)
    prefix = f"{cfg.raw_prefix}/{raw_dir}/date={data_date}/"
    table_id = f"{cfg.project}.{cfg.bronze}.{table}"

    batch_ids = list_batch_ids(prefix)
    if not batch_ids:
        return 0
    latest, older = batch_ids[-1], batch_ids[:-1]

    client = bigquery.Client(project=cfg.project)
    already_loaded = table_exists(client, table_id) and count_batch_rows(client, table_id, latest)

    rows = 0
    if not already_loaded:
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        uri = f"gs://{cfg.bucket}/{prefix}batch_id={latest}/*"

        def load() -> int:
            job = client.load_table_from_uri(uri, table_id, job_config=config)
            job.result()
            return job.output_rows or 0

        rows = call_with_retry(load)

    if older:  # only after the new batch is safe in Bronze
        delete_batches(client, table_id, older)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--table", choices=TABLES)
    args = parser.parse_args()

    for table in [args.table] if args.table else TABLES:
        print(f"{table} {args.date}: {load_day(table, args.date)} rows -> Bronze")


if __name__ == "__main__":
    main()
