"""Unit tests for pure pipeline functions; no GCP needed."""

from datetime import datetime
from importlib import import_module

import pandas as pd
import pytest
import sqlalchemy
from google.api_core import exceptions

utils = import_module("src.1_source.utils")
retry = import_module("src.1_source.retry")
raw_writer = import_module("src.2_ingestion.raw_writer")
pg_tables = import_module("src.2_ingestion.postgres_tables")
load_bronze = import_module("src.3_storage.load_bronze")
run_dbt = import_module("src.4_transform.run_dbt")
eda = import_module("src.5_serving.eda")


@pytest.mark.parametrize("value", ["2026-10-01", "2024-02-29"])
def test_valid_date_accepts_real_dates(value: str) -> None:
    assert utils.valid_date(value) == value


@pytest.mark.parametrize("value", ["2026-02-30", "2026-1-01", "20261001", ""])
def test_valid_date_rejects_bad_dates(value: str) -> None:
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        utils.valid_date(value)


def test_is_transient() -> None:
    assert retry.is_transient(exceptions.ServiceUnavailable("busy"))
    assert not retry.is_transient(exceptions.NotFound("no table"))


def test_postgres_errors_retry_only_on_network_problems() -> None:
    def error(message: str) -> sqlalchemy.exc.OperationalError:
        return sqlalchemy.exc.OperationalError("SELECT 1", {}, Exception(message))

    assert retry.is_transient(error("timeout expired"))
    assert not retry.is_transient(error("password authentication failed"))


def at(value: str) -> datetime:
    return datetime.fromisoformat(value)  # naive, like Postgres updated_at


def test_pg_window_first_run_reads_everything() -> None:
    assert pg_tables.read_window("2026-10-15", None) == (None, at("2026-10-16"))


def test_pg_window_starts_at_watermark_minus_lookback() -> None:
    start, end = pg_tables.read_window("2026-10-15", at("2026-10-14T23:59"))
    assert (start, end) == (at("2026-10-13T23:59"), at("2026-10-16"))


def test_raw_path() -> None:
    path = raw_writer.raw_path("orders", "2026-10-01", "b1", prefix="raw/stylehub")
    assert path == "raw/stylehub/orders/date=2026-10-01/batch_id=b1/orders.parquet"


def test_batch_ids_from_folders_sorted_and_unique() -> None:
    folders = ["p/batch_id=2/", "p/batch_id=1/", "p/other/", "p/batch_id=1/"]
    assert load_bronze.batch_ids_from_folders(folders) == ["1", "2"]


def test_staging_and_partition_ids() -> None:
    assert load_bronze.staging_table_id("proj.ds.orders") == "proj.ds._stg_orders"
    assert load_bronze.partition_id("proj.ds.orders", "2026-10-01") == "proj.ds.orders$20261001"


def test_dbt_build_command_selects_layer_tag() -> None:
    args = run_dbt.build_command("silver")
    assert args[0] == "build"
    assert "--fail-fast" in args
    assert args[args.index("--indirect-selection") + 1] == "cautious"
    assert args[-2:] == ["--select", "tag:silver"]
    assert args[args.index("--target-path") + 1].endswith("silver")
    assert args[args.index("--log-path") + 1].replace("\\", "/").endswith("logs/dbt/silver")


def eda_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 3],
            "user_id": [10, 10, 11, 11],
            "category": ["Jeans", "Jeans", "Tops", "Tops"],
            "sale_price": [10.0, 20.0, 30.0, 30.0],
            "quantity": [1, 2, 1, 1],
            "amount": [10.0, 40.0, 30.0, 30.0],
            "cost": [5.0, 25.0, 10.0, 10.0],
        }
    )


def test_eda_quality_duplicates_and_issues() -> None:
    df = eda_frame()
    assert eda.quality_report(df).loc["amount", "missing"] == 0
    assert eda.duplicate_counts(df, ["id"]) == {"full_rows": 1, "key": 1}
    issues = eda.data_issues(df)
    assert issues["amount != sale_price * quantity"] == 0
    assert issues["sold below cost"] == 1


def test_eda_iqr_outliers_and_capping() -> None:
    values = pd.DataFrame({"amount": [10.0, 11.0, 12.0, 13.0, 100.0]})
    lower, upper = eda.iqr_bounds(values["amount"])
    assert (lower, upper) == (8.0, 16.0)
    assert eda.outlier_summary(values, ["amount"]).loc["amount", "n_out"] == 1
    capped = eda.cap_outliers(values, ["amount"])
    assert len(capped) == len(values)
    assert capped["amount"].max() == upper


def test_eda_kpis_by_category() -> None:
    kpis = eda.kpis_by(eda_frame(), ["category"])
    assert kpis.loc["Tops", "revenue"] == 60.0
    assert kpis.loc["Jeans", "customers"] == 1


def test_jev_review_asks_one_or_two_judgments_per_finding() -> None:
    jev_review = import_module("include.scripts.jev_review")
    findings = [
        {"id": "o1", "kind": "optimization", "file": "a.py:1", "text": "x"},
        {"id": "v1", "kind": "vulnerability", "file": "b.py:2", "text": "y"},
        {"id": "e1", "kind": "expansion", "file": "src/3_storage", "text": "z"},
    ]
    assert sorted(jev_review.questions_for(findings)) == [
        "e1.value",
        "o1.impact",
        "v1.exploitable",
        "v1.severity",
    ]
