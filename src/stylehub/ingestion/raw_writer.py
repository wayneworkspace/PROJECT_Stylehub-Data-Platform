"""Write a DataFrame to the Raw Zone on GCS, append-only, with metadata columns.

Ingestion only extracts and writes raw data. No transforming here.
"""

from datetime import UTC, datetime

import google.cloud.storage as storage
import pandas as pd

from stylehub.common.clients import gcs_client
from stylehub.common.config import Settings, resolve
from stylehub.common.ids import new_id
from stylehub.common.retry import call_with_retry


def add_metadata(df: pd.DataFrame, source: str, batch_id: str) -> pd.DataFrame:
    out = df.copy()
    out["_ingested_at"] = datetime.now(UTC)
    out["_source"] = source
    out["_batch_id"] = batch_id
    return out


def raw_path(table: str, data_date: str, batch_id: str, prefix: str | None = None) -> str:
    if prefix is None:
        prefix = resolve(None).raw_prefix
    return f"{prefix}/{table}/date={data_date}/batch_id={batch_id}/{table}.parquet"


def write_raw(
    df: pd.DataFrame,
    table: str,
    data_date: str,
    source: str,
    client: storage.Client | None = None,
    cfg: Settings | None = None,
) -> str:
    """Write a new parquet file. Every run gets a new batch_id and never overwrites."""
    cfg = resolve(cfg)
    batch_id = new_id()
    df = add_metadata(df, source, batch_id)

    data = df.to_parquet(index=False)  # no path given: pandas returns the file as bytes

    if client is None:
        client = gcs_client(cfg)
    bucket = client.bucket(cfg.bucket)
    path = raw_path(table, data_date, batch_id, cfg.raw_prefix)
    blob = bucket.blob(path)

    call_with_retry(lambda: blob.upload_from_string(data, content_type="application/octet-stream"))
    return f"gs://{bucket.name}/{path}"
