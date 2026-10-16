import io
from unittest.mock import MagicMock

import pandas as pd

from stylehub.ingestion import raw_writer
from stylehub.ingestion.raw_writer import add_metadata, raw_path


def test_add_metadata_adds_three_columns():
    df = pd.DataFrame({"id": [1, 2]})
    out = add_metadata(df, source="postgres", batch_id="b1")
    assert {"_ingested_at", "_source", "_batch_id"} <= set(out.columns)
    assert out["_batch_id"].unique().tolist() == ["b1"]


def test_add_metadata_does_not_mutate_input():
    df = pd.DataFrame({"id": [1]})
    add_metadata(df, source="postgres", batch_id="b1")
    assert list(df.columns) == ["id"]


def test_raw_path_layout():
    path = raw_path("orders", "2026-10-01", "b1")
    assert path == "raw/stylehub/orders/date=2026-10-01/batch_id=b1/orders.parquet"


def test_write_raw_uploads_one_parquet_file_with_the_metadata_columns(monkeypatch):
    bucket = MagicMock()
    bucket.name = "my-bucket"
    client = MagicMock()
    client.bucket.return_value = bucket
    monkeypatch.setattr(raw_writer.storage, "Client", lambda project: client)

    uri = raw_writer.write_raw(pd.DataFrame({"id": [1, 2]}), "orders", "2026-10-01", source="csv")

    assert uri.startswith("gs://my-bucket/raw/stylehub/orders/date=2026-10-01/batch_id=")
    uploaded = bucket.blob.return_value.upload_from_string.call_args.args[0]
    out = pd.read_parquet(io.BytesIO(uploaded))
    assert list(out.columns) == ["id", "_ingested_at", "_source", "_batch_id"]
    assert out["_source"].unique().tolist() == ["csv"]
    # the file remembers how many rows the source had, so Bronze can check it
    assert bucket.blob.return_value.metadata == {"source_rows": "2"}
