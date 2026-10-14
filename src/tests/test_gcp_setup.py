from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

from common.config import Settings
from storage import load_csv, setup_gcp


def make_settings() -> Settings:
    return Settings(
        project="p", bucket="b", raw_prefix="raw/stylehub", source="stylehub",
        bronze="stylehub_bronze", silver="stylehub_silver", gold="stylehub_gold",
        ops="stylehub_ops", location="asia-southeast1",
    )


def test_dataset_list_has_source_layers_and_ops():
    assert setup_gcp.dataset_ids(make_settings()) == [
        "stylehub", "stylehub_bronze", "stylehub_silver", "stylehub_gold", "stylehub_ops",
    ]


def test_existing_bucket_is_left_alone():
    client = MagicMock()
    assert setup_gcp.ensure_bucket(client, "b", "asia-southeast1") is False
    client.create_bucket.assert_not_called()


def test_missing_bucket_is_created_in_the_location():
    client = MagicMock()
    client.lookup_bucket.return_value = None
    assert setup_gcp.ensure_bucket(client, "b", "asia-southeast1") is True
    assert client.create_bucket.call_args.kwargs == {"location": "asia-southeast1"}


def test_existing_dataset_is_left_alone():
    client = MagicMock()
    assert setup_gcp.ensure_dataset(client, "stylehub_gold", "asia-southeast1") is False
    client.create_dataset.assert_not_called()


def test_missing_dataset_is_created_in_the_location():
    client = MagicMock(project="p")
    client.get_dataset.side_effect = NotFound("missing")
    assert setup_gcp.ensure_dataset(client, "stylehub_gold", "asia-southeast1") is True
    created = client.create_dataset.call_args.args[0]
    assert created.dataset_id == "stylehub_gold" and created.location == "asia-southeast1"


def test_table_name_comes_from_the_file_name():
    assert load_csv.table_name_for(Path("data/raw_data/order_items.csv")) == "order_items"


def test_find_csv_files_is_sorted_and_ignores_other_files(tmp_path):
    for name in ("users.csv", "orders.csv", "notes.txt"):
        (tmp_path / name).write_text("x")
    assert [p.name for p in load_csv.find_csv_files(tmp_path)] == ["orders.csv", "users.csv"]


def test_find_csv_files_fails_on_an_empty_folder(tmp_path):
    with pytest.raises(SystemExit):
        load_csv.find_csv_files(tmp_path)


def test_format_size():
    assert load_csv.format_size(512) == "512.0 B"
    assert load_csv.format_size(4_345_205) == "4.1 MB"


def test_upload_is_skipped_when_the_same_file_is_already_there(tmp_path):
    local = tmp_path / "orders.csv"
    local.write_text("id\n1\n")
    bucket = MagicMock()
    bucket.name = "b"
    bucket.get_blob.return_value = MagicMock(size=local.stat().st_size)
    uri = load_csv.upload_csv(bucket, local, "landing/stylehub/orders.csv")
    assert uri == "gs://b/landing/stylehub/orders.csv"
    bucket.blob.assert_not_called()


def test_upload_happens_when_the_file_is_new_or_a_different_size(tmp_path):
    local = tmp_path / "orders.csv"
    local.write_text("id\n1\n")
    bucket = MagicMock()
    bucket.name = "b"
    bucket.get_blob.return_value = None
    load_csv.upload_csv(bucket, local, "landing/stylehub/orders.csv")
    bucket.blob.return_value.upload_from_filename.assert_called_once_with(str(local))
    assert bucket.blob.return_value.chunk_size == load_csv.UPLOAD_CHUNK_BYTES
