"""Bronze keeps one snapshot per day: a re-run replaces that day's partition, never doubles it."""

from datetime import date
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound, ServiceUnavailable
from google.cloud import bigquery

from stylehub.bronze import load_bronze
from stylehub.bronze.load_bronze import batch_ids_from_folders, partition_id
from stylehub.common import retry

PREFIX = "raw/stylehub/orders/date=2026-10-01/"
DESTINATION = "my-project.stylehub_bronze.orders$20261001"
STAGING = "my-project.stylehub_bronze._stg_orders"


def folders(*batch_ids: str) -> list[str]:
    return [f"{PREFIX}batch_id={b}/" for b in batch_ids]


def test_batch_ids_are_sorted_oldest_first():
    found = batch_ids_from_folders(folders("20261001T030000-bbbbbb", "20261001T020000-aaaaaa"))
    assert found == ["20261001T020000-aaaaaa", "20261001T030000-bbbbbb"]


def test_batch_ids_ignore_folders_without_a_batch():
    assert batch_ids_from_folders([f"{PREFIX}readme/"]) == []


def test_partition_id_has_the_day_without_dashes():
    assert partition_id("p.d.orders", "2026-10-01") == "p.d.orders$20261001"


def prepare(monkeypatch, batches, load_fails=False):
    """Fake GCS and BigQuery. Return the fake client and the list of load jobs it received."""
    loads = []  # (uri, destination, job_config) of every load job (into the staging table)

    def load_table_from_uri(uri, destination, job_id, job_config):
        if load_fails:
            raise RuntimeError("load failed")
        loads.append((uri, destination, job_config))
        return MagicMock(output_rows=10)

    client = MagicMock()
    client.load_table_from_uri.side_effect = load_table_from_uri
    client.get_table.return_value = MagicMock(time_partitioning=None)  # the table already exists
    monkeypatch.setattr(load_bronze.bigquery, "Client", lambda project: client)
    monkeypatch.setattr(load_bronze, "list_batch_ids", lambda prefix, cfg=None: batches)
    monkeypatch.setattr(load_bronze, "count_raw_rows", lambda prefix, cfg=None: 10)  # fake loads 10
    return client, loads


def test_list_batch_ids_reads_the_sub_folders_from_gcs(monkeypatch):
    blobs = MagicMock()
    blobs.__iter__.return_value = iter([])
    blobs.prefixes = set(folders("b", "a"))
    client = MagicMock()
    client.list_blobs.return_value = blobs
    monkeypatch.setattr(load_bronze.storage, "Client", lambda project: client)

    assert load_bronze.list_batch_ids(PREFIX) == ["a", "b"]
    assert client.list_blobs.call_args.kwargs == {"prefix": PREFIX, "delimiter": "/"}


def test_the_latest_batch_replaces_the_partition_of_the_day(monkeypatch):
    client, loads = prepare(monkeypatch, ["a", "b"])
    assert load_bronze.load_day("orders", "2026-10-01") == 10
    assert len(loads) == 1
    uri, destination, config = loads[0]
    assert uri == f"gs://my-bucket/{PREFIX}batch_id=b/*"  # the newest batch only
    assert destination == STAGING  # never straight into the partition Silver reads
    assert config.write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    copy = client.copy_table.call_args
    assert copy.args == (STAGING, DESTINATION)  # publish: staging replaces the day's partition
    assert copy.kwargs["job_config"].write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE
    client.delete_table.assert_called_once_with(STAGING, not_found_ok=True)


def test_older_batches_need_no_delete_query(monkeypatch):
    client, loads = prepare(monkeypatch, ["a", "b", "c"])
    load_bronze.load_day("orders", "2026-10-01")
    client.query.assert_not_called()  # the old DELETE step is gone: truncate replaces the day


def test_running_a_day_twice_loads_the_same_partition_both_times(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    assert load_bronze.load_day("orders", "2026-10-01") == 10
    assert load_bronze.load_day("orders", "2026-10-01") == 10
    assert [load[1] for load in loads] == [STAGING, STAGING]
    assert [c.args[1] for c in client.copy_table.call_args_list] == [DESTINATION, DESTINATION]
    assert all(
        load[2].write_disposition == bigquery.WriteDisposition.WRITE_TRUNCATE for load in loads
    )


def test_a_failed_load_raises_and_changes_nothing_else(monkeypatch):
    client, loads = prepare(monkeypatch, ["a", "b"], load_fails=True)
    with pytest.raises(RuntimeError):
        load_bronze.load_day("orders", "2026-10-01")
    client.query.assert_not_called()


def test_first_load_creates_the_table_by_itself(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    load_bronze.load_day("orders", "2026-10-01")
    # The expiration is set on the Bronze table, AFTER the partition was published.
    assert client.get_table.call_args.args == ("my-project.stylehub_bronze.orders",)


def test_old_snapshots_expire_after_the_retention_days(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    table = MagicMock()
    table.time_partitioning = bigquery.TimePartitioning(type_="DAY")
    client.get_table.return_value = table
    load_bronze.load_day("orders", "2026-10-01")
    days = table.time_partitioning.expiration_ms / (24 * 3600 * 1000)
    assert days == load_bronze.SNAPSHOT_RETENTION_DAYS
    client.update_table.assert_called_once_with(table, ["time_partitioning"])


def test_an_expiration_you_set_by_hand_is_kept(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    table = MagicMock()
    table.time_partitioning = bigquery.TimePartitioning(type_="DAY", expiration_ms=1000)
    client.get_table.return_value = table
    load_bronze.load_day("orders", "2026-10-01")
    client.update_table.assert_not_called()


def test_a_failed_expiration_update_does_not_fail_the_load(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    # 1st call: the table exists. 2nd call (the expiration update) fails.
    client.get_table.side_effect = [MagicMock(), RuntimeError("no permission")]
    assert load_bronze.load_day("orders", "2026-10-01") == 10


def test_no_raw_files_loads_nothing(monkeypatch):
    client, loads = prepare(monkeypatch, [])
    assert load_bronze.load_day("orders", "2026-10-01") == 0
    assert loads == []


def test_a_retried_load_uses_the_same_job_id(monkeypatch):
    prepare(monkeypatch, ["a"])
    client = MagicMock()
    client.load_table_from_uri.side_effect = [ServiceUnavailable("busy"), MagicMock(output_rows=7)]
    monkeypatch.setattr(load_bronze.bigquery, "Client", lambda project: client)
    monkeypatch.setattr(load_bronze, "count_raw_rows", lambda prefix, cfg=None: 7)
    monkeypatch.setattr(
        load_bronze, "call_with_retry", lambda func: retry.call_with_retry(func, sleep=lambda s: 0)
    )

    assert load_bronze.load_day("orders", "2026-10-01") == 7
    ids = [call.kwargs["job_id"] for call in client.load_table_from_uri.call_args_list]
    assert len(ids) == 2 and ids[0] == ids[1] and ids[0].startswith("bronze_orders_")


def test_load_day_uses_the_client_it_is_given(monkeypatch):
    prepare(monkeypatch, ["a"])
    monkeypatch.setattr(
        load_bronze.bigquery, "Client", lambda project: pytest.fail("must use the given client")
    )
    monkeypatch.setattr(load_bronze, "count_raw_rows", lambda prefix, cfg=None: 3)
    client = MagicMock()
    client.load_table_from_uri.return_value = MagicMock(output_rows=3)
    assert load_bronze.load_day("orders", "2026-10-01", client=client) == 3


def test_a_wrong_date_is_refused(monkeypatch):
    prepare(monkeypatch, ["a"])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        load_bronze.load_day("orders", "2026-10-1")


def test_a_load_with_a_different_row_count_than_raw_fails(monkeypatch):
    prepare(monkeypatch, ["a"])
    monkeypatch.setattr(load_bronze, "count_raw_rows", lambda prefix, cfg=None: 12)  # fake loads 10
    with pytest.raises(load_bronze.RowCountMismatch, match="12 rows but Bronze got 10"):
        load_bronze.load_day("orders", "2026-10-01")


def test_a_bad_load_never_reaches_the_partition(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    monkeypatch.setattr(load_bronze, "count_raw_rows", lambda prefix, cfg=None: 12)
    with pytest.raises(load_bronze.RowCountMismatch):
        load_bronze.load_day("orders", "2026-10-01")
    client.copy_table.assert_not_called()  # the partition Silver reads is not touched
    client.delete_table.assert_not_called()  # staging is kept so you can look at it


def test_a_missing_bronze_table_is_created_before_the_copy(monkeypatch):
    client, loads = prepare(monkeypatch, ["a"])
    staging = MagicMock(schema=[bigquery.SchemaField("order_id", "INTEGER")])
    client.get_table.side_effect = [
        NotFound("no table"),
        staging,
        MagicMock(time_partitioning=None),
    ]
    load_bronze.load_day("orders", "2026-10-01")
    created = client.create_table.call_args.args[0]
    assert created.table_id == "orders" and created.time_partitioning.type_ == "DAY"
    assert [f.name for f in created.schema] == ["order_id"]


def test_a_day_older_than_the_retention_warns(caplog):
    today = date(2026, 10, 16)
    assert load_bronze.warn_if_partition_expires("2026-08-01", today=today) is True
    assert "delete this partition" in caplog.text
    assert load_bronze.warn_if_partition_expires("2026-10-01", today=today) is False


def test_a_raw_file_with_fewer_rows_than_the_source_had_is_refused(monkeypatch):
    parquet = MagicMock(metadata={"source_rows": "50"})
    parquet.name = "raw/orders/date=2026-10-01/batch_id=a/orders.parquet"
    parquet.open.return_value.__enter__.return_value = "file"
    client = MagicMock()
    client.list_blobs.return_value = [parquet]
    monkeypatch.setattr(load_bronze.storage, "Client", lambda project: client)
    monkeypatch.setattr(
        load_bronze.pq, "ParquetFile", lambda file: MagicMock(metadata=MagicMock(num_rows=42))
    )
    with pytest.raises(load_bronze.RowCountMismatch, match="source had 50 rows"):
        load_bronze.count_raw_rows("raw/orders/date=2026-10-01/batch_id=a/")


def test_count_raw_rows_adds_up_the_parquet_footers(monkeypatch):
    class Blob:
        def __init__(self, name):
            self.name = name

        def open(self, mode):
            raise AssertionError("only .parquet files may be opened")

    parquet = MagicMock()
    parquet.name = "raw/orders/date=2026-10-01/batch_id=a/orders.parquet"
    parquet.open.return_value.__enter__.return_value = "file"
    client = MagicMock()
    client.list_blobs.return_value = [parquet, Blob("raw/orders/_SUCCESS")]
    monkeypatch.setattr(load_bronze.storage, "Client", lambda project: client)
    monkeypatch.setattr(
        load_bronze.pq, "ParquetFile", lambda file: MagicMock(metadata=MagicMock(num_rows=42))
    )
    assert load_bronze.count_raw_rows("raw/orders/date=2026-10-01/batch_id=a/") == 42
