import pandas as pd

from ingestion.raw_writer import add_metadata, raw_path


def test_add_metadata_adds_three_columns():
    df = pd.DataFrame({"id": [1, 2]})
    out = add_metadata(df, source="postgres", batch_id="b1")
    assert {"_ingested_at", "_source", "_batch_id"} <= set(out.columns)
    assert out["_batch_id"].unique().tolist() == ["b1"]


def test_add_metadata_does_not_mutate_input():
    df = pd.DataFrame({"id": [1]})
    add_metadata(df, source="postgres", batch_id="b1")
    assert list(df.columns) == ["id"]


def test_raw_path_layout(monkeypatch):
    monkeypatch.setenv("RAW_PREFIX", "raw/stylehub")
    path = raw_path("orders", "2026-10-01", "b1")
    assert path == "raw/stylehub/orders/date=2026-10-01/batch_id=b1/orders.parquet"
