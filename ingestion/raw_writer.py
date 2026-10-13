"""Write a DataFrame to the Raw Zone on GCS, append-only, with metadata columns.

Ingestion only extracts and writes raw data. No transforming here.
"""

import io
import os
import uuid
from datetime import UTC, datetime

import pandas as pd
from google.cloud import storage


def new_batch_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


def add_metadata(df: pd.DataFrame, source: str, batch_id: str) -> pd.DataFrame:
    out = df.copy()
    out["_ingested_at"] = datetime.now(UTC)
    out["_source"] = source
    out["_batch_id"] = batch_id
    return out


def raw_path(table: str, data_date: str, batch_id: str) -> str:
    prefix = os.environ.get("RAW_PREFIX", "raw/stylehub")
    return f"{prefix}/{table}/date={data_date}/batch_id={batch_id}/{table}.parquet"


def write_raw(df: pd.DataFrame, table: str, data_date: str, source: str) -> str:
    """Write a new parquet file. Every run gets a new batch_id and never overwrites."""
    batch_id = new_batch_id()
    df = add_metadata(df, source, batch_id)

    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    bucket = storage.Client().bucket(os.environ["GCS_BUCKET"])
    path = raw_path(table, data_date, batch_id)
    bucket.blob(path).upload_from_file(buffer, content_type="application/octet-stream")
    return f"gs://{bucket.name}/{path}"
