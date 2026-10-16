"""Load the Raw files of one day into Bronze. Safe to re-run.

Bronze keeps ONE snapshot per day: the latest Raw batch of that day, in a day partition.
The load is Write-Audit-Publish: load into a staging table, check the row count against the Raw
file, and only then copy it over the day's partition. A bad load never reaches Silver.
Old snapshots expire after SNAPSHOT_RETENTION_DAYS; Raw on GCS keeps every batch.

Usage: python -m stylehub.bronze.load_bronze --date 2026-10-01 [--table orders]
"""

import argparse
import logging

import pyarrow.parquet as pq
from google.cloud import bigquery

from stylehub.common.bq import table_exists
from stylehub.common.clients import bq_client, gcs_client
from stylehub.common.config import Settings, resolve
from stylehub.common.dates import date_arg, valid_date
from stylehub.common.logs import setup_cli_logging
from stylehub.common.retry import call_with_retry
from stylehub.ingestion.csv_tables import CSV_TABLES

log = logging.getLogger(__name__)

SNAPSHOT_RETENTION_DAYS = 30


def batch_ids_from_folders(folders: list[str]) -> list[str]:
    """The batch ids in Raw folder names like .../batch_id=<id>/, oldest first."""
    ids = set()
    for folder in folders:
        last = folder.rstrip("/").rsplit("/", 1)[-1]
        if last.startswith("batch_id="):
            ids.add(last.removeprefix("batch_id="))
    return sorted(ids)


def list_batch_ids(prefix: str, cfg: Settings | None = None) -> list[str]:
    """The batch ids of one table and one day, read from the Raw Zone on GCS."""
    cfg = resolve(cfg)
    client = gcs_client(cfg)

    def list_folders() -> list[str]:
        # With delimiter="/" GCS lists the sub-folders in .prefixes. The listing is lazy and
        # .prefixes is filled while it is read, so read it to the end first.
        blobs = client.list_blobs(cfg.bucket, prefix=prefix, delimiter="/")
        list(blobs)
        return sorted(blobs.prefixes)

    return batch_ids_from_folders(call_with_retry(list_folders))


class RowCountMismatch(RuntimeError):
    """Bronze did not get the same number of rows as the Raw file holds."""


def count_raw_rows(prefix: str, cfg: Settings | None = None) -> int:
    """The rows in the Parquet files under one Raw folder, read from the file footers only."""
    cfg = resolve(cfg)
    client = gcs_client(cfg)

    def count() -> int:
        total = 0
        for blob in client.list_blobs(cfg.bucket, prefix=prefix):
            if blob.name.endswith(".parquet"):
                with blob.open("rb") as file:
                    total += pq.ParquetFile(file).metadata.num_rows
        return total

    return call_with_retry(count)


def staging_table_id(table_id: str) -> str:
    """The staging table next to a Bronze table: project.dataset._stg_<table>."""
    project_dataset, _, name = table_id.rpartition(".")
    return f"{project_dataset}._stg_{name}"


def ensure_bronze_table(client: bigquery.Client, table_id: str, staging_id: str) -> None:
    """Create the day-partitioned Bronze table (empty, same columns as staging) if it is missing.

    A copy job can write into a partition only when the table already exists.
    """
    if table_exists(client, table_id):
        return
    staging = call_with_retry(lambda: client.get_table(staging_id))
    table = bigquery.Table(table_id, schema=staging.schema)
    # BigQuery deletes a day older than SNAPSHOT_RETENTION_DAYS by itself (counted from its date).
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        expiration_ms=SNAPSHOT_RETENTION_DAYS * 24 * 3600 * 1000,
    )
    call_with_retry(lambda: client.create_table(table, exists_ok=True))


def drop_staging(client: bigquery.Client, staging_id: str) -> None:
    """Delete the staging table. Housekeeping: it never fails a good load."""
    try:
        call_with_retry(lambda: client.delete_table(staging_id, not_found_ok=True))
    except Exception as exc:  # housekeeping must not fail a good load
        log.warning("Could not delete %s: %s", staging_id, exc, exc_info=True)


def partition_id(table_id: str, data_date: str) -> str:
    """The partition of one day: project.dataset.table$YYYYMMDD."""
    return f"{table_id}${data_date.replace('-', '')}"


def load_day(
    table: str,
    data_date: str,
    client: bigquery.Client | None = None,
    cfg: Settings | None = None,
) -> int:
    """Make Bronze hold the latest Raw batch of one table and one day. Return the rows loaded.

    The day's partition is replaced as a whole, so this is safe to run again and again.
    Returns 0 when there is no Raw file for that day (nothing is changed then); the Bronze step
    treats 0 as a failure. Raises RowCountMismatch if Bronze and the Raw file disagree.
    Pass `client` to use your own BigQuery client (a test passes a fake one).
    """
    valid_date(data_date)
    cfg = resolve(cfg)
    prefix = f"{cfg.raw_prefix}/{table}/date={data_date}/"
    table_id = f"{cfg.project}.{cfg.bronze}.{table}"

    batch_ids = list_batch_ids(prefix, cfg)
    if not batch_ids:
        return 0
    latest = batch_ids[-1]

    if client is None:
        client = bq_client(cfg)
    staging_id = staging_table_id(table_id)
    # 1. Load the batch into staging. WRITE_TRUNCATE: a re-run starts from an empty staging table.
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    uri = f"gs://{cfg.bucket}/{prefix}batch_id={latest}/*"

    def load() -> int:
        # WRITE_TRUNCATE: a retry of the whole job gives the same table, so it is safe.
        job = client.load_table_from_uri(uri, staging_id, job_config=config, location=cfg.location)
        job.result()
        return job.output_rows or 0

    loaded = call_with_retry(load)

    # 2. Audit: staging must hold exactly the rows of the Raw file. The partition is untouched.
    expected = count_raw_rows(f"{prefix}batch_id={latest}/", cfg)
    if loaded != expected:
        raise RowCountMismatch(
            f"{table} {data_date}: Raw file has {expected} rows but Bronze got {loaded}. "
            f"The partition was not changed; the bad load is kept in {staging_id}."
        )

    # 3. Publish: replace the day's partition with the audited staging table, in one step.
    ensure_bronze_table(client, table_id, staging_id)
    copy_config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    destination = partition_id(table_id, data_date)
    call_with_retry(
        lambda: client.copy_table(
            staging_id, destination, job_config=copy_config, location=cfg.location
        ).result()
    )
    drop_staging(client, staging_id)
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, type=date_arg, help="YYYY-MM-DD")
    parser.add_argument("--table", choices=CSV_TABLES)
    args = parser.parse_args()
    setup_cli_logging()

    for table in [args.table] if args.table else CSV_TABLES:
        log.info("%s %s: %s rows -> Bronze", table, args.date, load_day(table, args.date))


if __name__ == "__main__":
    main()
