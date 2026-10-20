"""Load one day's latest Raw batch into Bronze: write, audit, publish."""

from importlib import import_module

import google.cloud.storage as storage
import pyarrow.parquet as pq
from google.cloud import bigquery

get_logger = import_module("src.0_utils.logger").get_logger

bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")

log = get_logger(__name__)

SNAPSHOT_RETENTION_DAYS = 30


SUCCESS_MARKER = "_SUCCESS"  # written last by writers that split a batch into part files


def complete_batch_ids(names: list[str]) -> list[str]:
    """Batch ids from Raw file names, oldest first, without unfinished batches.

    A batch of part files counts only once it has _SUCCESS, so a run that
    failed half way is never loaded; a one-file batch is complete when it exists.
    """
    files: dict[str, set[str]] = {}
    for name in names:
        folder, _, file = name.rpartition("/")
        batch = folder.rsplit("/", 1)[-1]
        if batch.startswith("batch_id="):
            files.setdefault(batch.removeprefix("batch_id="), set()).add(file)
    return sorted(
        batch
        for batch, found in files.items()
        if SUCCESS_MARKER in found or not any(f.startswith("part_") for f in found)
    )


def list_batch_ids(gcs: storage.Client, prefix: str, cfg: config.Settings) -> list[str]:
    """Complete batch ids of one table and day in the Raw Zone."""
    names = retry.call_with_retry(
        lambda: [b.name for b in gcs.list_blobs(cfg.bucket, prefix=prefix)]
    )
    return complete_batch_ids(names)


class RowCountMismatch(RuntimeError):
    """Bronze row count differs from the Raw file row count."""


def count_raw_rows(gcs: storage.Client, prefix: str, cfg: config.Settings) -> int:
    """Rows in a Raw folder's Parquet files, read from footers."""

    def count() -> int:
        total = 0
        for blob in gcs.list_blobs(cfg.bucket, prefix=prefix):
            if blob.name.endswith(".parquet"):
                with blob.open("rb") as file:
                    total += pq.ParquetFile(file).metadata.num_rows
        return total

    return retry.call_with_retry(count)


def staging_table_id(table_id: str) -> str:
    """Staging table next to a Bronze table: dataset._stg_<table>."""
    project_dataset, _, name = table_id.rpartition(".")
    return f"{project_dataset}._stg_{name}"


def ensure_bronze_table(
    client: bigquery.Client, table_id: str, staging_id: str, keep_days: int | None
) -> None:
    """Create the day-partitioned Bronze table if missing; copies need it."""
    if bq.table_exists(client, table_id):
        return
    staging = retry.call_with_retry(lambda: client.get_table(staging_id))
    table = bigquery.Table(table_id, schema=staging.schema)
    # Snapshots expire after keep_days; incremental partitions never expire.
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        expiration_ms=keep_days * 24 * 3600 * 1000 if keep_days else None,
    )
    retry.call_with_retry(lambda: client.create_table(table, exists_ok=True))


def drop_staging(client: bigquery.Client, staging_id: str) -> None:
    """Delete the staging table; a failure here only warns."""
    try:
        retry.call_with_retry(lambda: client.delete_table(staging_id, not_found_ok=True))
    except Exception as exc:  # housekeeping must not fail a good load
        log.warning("Could not delete %s: %s", staging_id, exc, exc_info=True)


def partition_id(table_id: str, data_date: str) -> str:
    """Partition id of one day: project.dataset.table$YYYYMMDD."""
    return f"{table_id}${data_date.replace('-', '')}"


def load_day(
    table: str,
    data_date: str,
    cfg: config.Settings,
    keep_days: int | None = SNAPSHOT_RETENTION_DAYS,
) -> int:
    """Replace one day's Bronze partition; return rows, 0 if no file."""
    prefix = f"{cfg.raw_prefix}/{table}/date={data_date}/"
    table_id = f"{cfg.project}.{cfg.bronze}.{table}"

    gcs = config.gcs_client(cfg)
    batch_ids = list_batch_ids(gcs, prefix, cfg)
    if not batch_ids:
        return 0
    latest = batch_ids[-1]

    client = config.bq_client(cfg)
    staging_id = staging_table_id(table_id)
    # 1. Write: load the batch into an empty staging table.
    load_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    uri = f"gs://{cfg.bucket}/{prefix}batch_id={latest}/*.parquet"  # not the _SUCCESS marker

    def load() -> int:
        # WRITE_TRUNCATE makes a retried load job safe.
        job = client.load_table_from_uri(
            uri, staging_id, job_config=load_config, location=cfg.location
        )
        job.result()
        return job.output_rows or 0

    loaded = retry.call_with_retry(load)

    # 2. Audit: staging rows must match the Raw file.
    expected = count_raw_rows(gcs, f"{prefix}batch_id={latest}/", cfg)
    if loaded != expected:
        raise RowCountMismatch(
            f"{table} {data_date}: Raw file has {expected} rows but Bronze got {loaded}. "
            f"The partition was not changed; the bad load is kept in {staging_id}."
        )

    # 3. Publish: copy audited staging over the day's partition.
    ensure_bronze_table(client, table_id, staging_id, keep_days)
    copy_config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    destination = partition_id(table_id, data_date)
    retry.call_with_retry(
        lambda: client.copy_table(
            staging_id, destination, job_config=copy_config, location=cfg.location
        ).result()
    )
    drop_staging(client, staging_id)
    return loaded
