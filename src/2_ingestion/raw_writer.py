"""Write DataFrames to the Raw Zone on GCS, append-only."""

from datetime import UTC, datetime
from importlib import import_module

import pandas as pd
import pyarrow as pa

config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")
utils = import_module("src.1_source.utils")


def raw_path(
    table: str, data_date: str, batch_id: str, prefix: str, part: str | None = None
) -> str:
    """One file per batch, or one per part when several tasks share a batch."""
    return f"{prefix}/{table}/date={data_date}/batch_id={batch_id}/{part or table}.parquet"


def write_raw(
    df: pd.DataFrame,
    table: str,
    data_date: str,
    cfg: config.Settings,
    source: str = "csv",
    batch_id: str | None = None,
    part: str | None = None,
    schema: pa.Schema | None = None,
) -> str:
    """Write a Parquet file with metadata columns; a new batch_id unless given.

    schema fixes the column types, so every part of a batch has the same ones.
    """
    batch_id = batch_id or utils.new_id()
    df = df.assign(_ingested_at=datetime.now(UTC), _source=source, _batch_id=batch_id)
    if schema is not None:
        schema = schema.append(pa.field("_ingested_at", pa.timestamp("us", tz="UTC")))
        schema = schema.append(pa.field("_source", pa.string()))
        schema = schema.append(pa.field("_batch_id", pa.string()))
    data = df.to_parquet(index=False, schema=schema)  # no path: pandas returns the bytes

    bucket = config.gcs_client(cfg).bucket(cfg.bucket)
    path = raw_path(table, data_date, batch_id, cfg.raw_prefix, part)
    blob = bucket.blob(path)

    retry.call_with_retry(
        lambda: blob.upload_from_string(data, content_type="application/octet-stream")
    )
    return f"gs://{bucket.name}/{path}"


def mark_batch_complete(table: str, data_date: str, batch_id: str, cfg: config.Settings) -> None:
    """Write _SUCCESS after the last part file; Bronze ignores part batches without it."""
    bucket = config.gcs_client(cfg).bucket(cfg.bucket)
    path = f"{cfg.raw_prefix}/{table}/date={data_date}/batch_id={batch_id}/_SUCCESS"
    blob = bucket.blob(path)
    retry.call_with_retry(lambda: blob.upload_from_string(b"", content_type="text/plain"))
