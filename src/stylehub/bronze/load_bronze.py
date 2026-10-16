"""Load the Raw files of one day into Bronze. Safe to re-run.

Each ingest writes a new batch under the day's Raw folder. Bronze keeps ONE snapshot per day:
the latest batch of that day. Bronze tables are partitioned by day (ingestion time).

The load is Write-Audit-Publish. The batch is first loaded into a staging table
(`_stg_<table>`), the row count is checked against the Raw file, and ONLY THEN the staging table is
copied over the day's partition (WRITE_TRUNCATE). A bad or partial load never reaches the partition
that Silver reads. Running a day twice gives the same rows (no doubling). Different days stay side
by side.

Silver reads only the NEWEST snapshot (dbt/macros/latest_bronze_snapshot.sql). Older snapshots are
kept for SNAPSHOT_RETENTION_DAYS days, as an audit copy, and then BigQuery deletes them by itself.
The Raw Zone on GCS keeps every batch, so nothing is lost.

Old Bronze tables that are NOT partitioned must be dropped once and rebuilt from Raw
(see docs/ops/TROUBLESHOOTING.md).

Usage: python -m stylehub.bronze.load_bronze --date 2026-10-01 [--table orders]
"""

import argparse
import logging
from datetime import UTC, date, datetime

import google.cloud.storage as storage
import pyarrow.parquet as pq
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from stylehub.common.bq import load_job_once
from stylehub.common.config import Settings, resolve
from stylehub.common.dates import date_arg, valid_date
from stylehub.common.ids import new_job_id
from stylehub.common.logs import setup_cli_logging
from stylehub.common.retry import call_with_retry

log = logging.getLogger(__name__)

TABLES = ("orders", "order_items", "products", "users")
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
    client = storage.Client(project=cfg.project)

    def list_folders() -> list[str]:
        # With delimiter="/" GCS lists the sub-folders in .prefixes. The listing is lazy and
        # .prefixes is filled while it is read, so read it to the end first.
        blobs = client.list_blobs(cfg.bucket, prefix=prefix, delimiter="/")
        for _ in blobs:
            pass
        return sorted(blobs.prefixes)

    return batch_ids_from_folders(call_with_retry(list_folders))


def ensure_snapshot_expiration(client: bigquery.Client, table_id: str) -> None:
    """Let BigQuery delete day-partitions older than SNAPSHOT_RETENTION_DAYS. Never fails a load.

    Only sets it when the table has no expiration yet, so a value you chose by hand is kept.
    """
    try:
        table = call_with_retry(lambda: client.get_table(table_id))
        partitioning = table.time_partitioning
        if partitioning is None or partitioning.expiration_ms:
            return
        partitioning.expiration_ms = SNAPSHOT_RETENTION_DAYS * 24 * 3600 * 1000
        table.time_partitioning = partitioning
        call_with_retry(lambda: client.update_table(table, ["time_partitioning"]))
    except Exception as exc:  # housekeeping must not fail a good load
        log.warning(
            "Could not set the partition expiration of %s: %s", table_id, exc, exc_info=True
        )


class RowCountMismatch(RuntimeError):
    """Bronze did not get the same number of rows as the Raw file holds."""


def warn_if_partition_expires(data_date: str, today: date | None = None) -> bool:
    """Warn when the day is older than the snapshot retention. Return True if it warned.

    The partition expiration counts from the partition's own date, so BigQuery deletes a
    partition that is loaded for a day older than SNAPSHOT_RETENTION_DAYS soon after the load.
    """
    today = today or datetime.now(UTC).date()
    age_days = (today - date.fromisoformat(data_date)).days
    if age_days <= SNAPSHOT_RETENTION_DAYS:
        return False
    log.warning(
        "%s is %d days old, more than SNAPSHOT_RETENTION_DAYS (%d). BigQuery may delete this "
        "partition by itself right after the load. Raise the retention first if you need it.",
        data_date,
        age_days,
        SNAPSHOT_RETENTION_DAYS,
    )
    return True


def count_raw_rows(prefix: str, cfg: Settings | None = None) -> int:
    """The rows in the Parquet files under one Raw folder, read from the file footers only.

    A file that remembers how many rows the source had (blob metadata "source_rows", set by
    ingestion/raw_writer.py) must hold that many rows, else RowCountMismatch.
    """
    cfg = resolve(cfg)
    client = storage.Client(project=cfg.project)

    def count() -> int:
        total = 0
        for blob in client.list_blobs(cfg.bucket, prefix=prefix):
            if blob.name.endswith(".parquet"):
                with blob.open("rb") as file:
                    rows = pq.ParquetFile(file).metadata.num_rows
                remembered = (
                    blob.metadata.get("source_rows") if isinstance(blob.metadata, dict) else None
                )
                if remembered is not None and int(remembered) != rows:
                    raise RowCountMismatch(
                        f"{blob.name}: the source had {remembered} rows but the file holds {rows}"
                    )
                total += rows
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
    try:
        call_with_retry(lambda: client.get_table(table_id))
        return
    except NotFound:
        pass
    staging = call_with_retry(lambda: client.get_table(staging_id))
    table = bigquery.Table(table_id, schema=staging.schema)
    table.time_partitioning = bigquery.TimePartitioning(type_=bigquery.TimePartitioningType.DAY)
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
    warn_if_partition_expires(data_date)
    cfg = resolve(cfg)
    prefix = f"{cfg.raw_prefix}/{table}/date={data_date}/"
    table_id = f"{cfg.project}.{cfg.bronze}.{table}"

    batch_ids = list_batch_ids(prefix, cfg)
    if not batch_ids:
        return 0
    latest = batch_ids[-1]

    if client is None:
        client = bigquery.Client(project=cfg.project)
    staging_id = staging_table_id(table_id)
    # 1. Load the batch into staging. WRITE_TRUNCATE: a re-run starts from an empty staging table.
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    uri = f"gs://{cfg.bucket}/{prefix}batch_id={latest}/*"
    # One job id for all tries of a step: a retry after a lost answer must not run it twice.
    load_id = new_job_id(f"bronze_{table}")

    def load() -> int:
        job = load_job_once(
            client,
            lambda jid: client.load_table_from_uri(uri, staging_id, job_id=jid, job_config=config),
            load_id,
            cfg.location,
        )
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
    copy_id = new_job_id(f"bronze_copy_{table}")
    call_with_retry(
        lambda: load_job_once(
            client,
            lambda jid: client.copy_table(
                staging_id, destination, job_id=jid, job_config=copy_config, location=cfg.location
            ),
            copy_id,
            cfg.location,
        )
    )
    ensure_snapshot_expiration(client, table_id)
    drop_staging(client, staging_id)
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, type=date_arg, help="YYYY-MM-DD")
    parser.add_argument("--table", choices=TABLES)
    args = parser.parse_args()
    setup_cli_logging()

    for table in [args.table] if args.table else TABLES:
        log.info("%s %s: %s rows -> Bronze", table, args.date, load_day(table, args.date))


if __name__ == "__main__":
    main()
