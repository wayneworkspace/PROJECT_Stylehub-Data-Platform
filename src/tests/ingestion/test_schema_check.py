from decimal import Decimal

import pandas as pd
import pytest

from stylehub.ingestion.schema_check import (
    EXPECTED_SCHEMAS,
    SchemaError,
    column_kind,
    diff_schema,
    enforce_schema,
)

SAMPLE_VALUE = {
    "int": 1,
    "number": Decimal("1.50"),
    "text": "x",
    "datetime": pd.Timestamp("2026-10-01"),
}


def sample_frame(table: str, ids=(1, 2)) -> pd.DataFrame:
    """Rows that match EXPECTED_SCHEMAS exactly, with the types Postgres gives us."""
    columns = EXPECTED_SCHEMAS[table]
    rows = [
        {col: (i if col == "id" else SAMPLE_VALUE[kind]) for col, kind in columns.items()}
        for i in ids
    ]
    return pd.DataFrame(rows)


def test_matching_schema_passes_unchanged():
    df = sample_frame("orders")
    assert enforce_schema(df, "orders") is df


def test_new_column_only_warns(caplog):
    df = sample_frame("orders").assign(coupon_code="SALE")
    assert enforce_schema(df, "orders") is df
    assert "coupon_code" in caplog.text


def test_removed_column_fails_and_names_it():
    df = sample_frame("orders").drop(columns=["num_of_item"])
    with pytest.raises(SchemaError, match="num_of_item"):
        enforce_schema(df, "orders")


def test_renamed_column_is_explained():
    df = sample_frame("orders").rename(columns={"num_of_item": "order_total"})
    with pytest.raises(SchemaError) as error:
        enforce_schema(df, "orders")
    assert "num_of_item" in str(error.value) and "order_total" in str(error.value)
    assert "renamed" in str(error.value)


def test_type_change_fails():
    df = sample_frame("orders").assign(num_of_item="12.50")  # was a number, now text
    with pytest.raises(SchemaError, match=r"num_of_item \(int -> text\)"):
        enforce_schema(df, "orders")


def test_absorb_fills_missing_columns_with_null_and_does_not_change_the_input():
    df = sample_frame("orders").drop(columns=["num_of_item"])
    out = enforce_schema(df, "orders", on_change="absorb")
    assert out["num_of_item"].isna().all()
    assert "num_of_item" not in df.columns


def test_absorb_lets_a_type_change_pass(caplog):
    df = sample_frame("orders").assign(num_of_item="12.50")
    out = enforce_schema(df, "orders", on_change="absorb")
    assert out["num_of_item"].tolist() == ["12.50", "12.50"]
    assert "absorbing" in caplog.text


def test_table_without_expected_schema_is_not_checked():
    df = pd.DataFrame({"anything": [1]})
    assert enforce_schema(df, "some_other_table") is df


def test_empty_result_checks_names_but_not_types():
    df = sample_frame("orders").iloc[0:0]  # no rows: every column is empty
    assert not diff_schema(df, EXPECTED_SCHEMAS["orders"]).is_breaking
    with pytest.raises(SchemaError):
        enforce_schema(df.drop(columns=["status"]), "orders")


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        enforce_schema(sample_frame("orders"), "orders", on_change="ignore")


@pytest.mark.parametrize(
    ("series", "kind"),
    [
        (pd.Series([1, 2]), "int"),
        (pd.Series([1.5]), "number"),
        (pd.Series([Decimal("1.5")]), "number"),
        (pd.Series(["a"]), "text"),
        (pd.Series(pd.to_datetime(["2026-10-01"])), "datetime"),
        (pd.Series([None, None]), None),
        (pd.Series([True, False]), "bool"),
        (pd.Series([1, None], dtype="Int64"), "int"),  # BigQuery gives nullable integers
        (pd.Series([1, "a"]), "mixed-integer"),  # not one kind: reported as a type change
    ],
)
def test_column_kind(series, kind):
    assert column_kind(series) == kind


def test_order_items_sample_matches_its_schema():
    assert not diff_schema(sample_frame("order_items"), EXPECTED_SCHEMAS["order_items"]).added


def test_an_empty_column_gets_the_expected_type_so_parquet_does_not_write_null():
    df = sample_frame("orders").assign(shipped_at=None, num_of_item=None, status=None)
    out = enforce_schema(df, "orders")
    assert str(out["shipped_at"].dtype) == "datetime64[ns, UTC]"
    assert str(out["num_of_item"].dtype) == "Int64"
    assert str(out["status"].dtype) == "string"
    assert df["shipped_at"].isna().all() and df["shipped_at"].dtype == object  # input unchanged


def test_absorbed_missing_columns_get_their_type_too():
    df = sample_frame("orders").drop(columns=["num_of_item"])
    out = enforce_schema(df, "orders", on_change="absorb")
    assert str(out["num_of_item"].dtype) == "Int64"


def test_users_age_is_part_of_the_contract_because_silver_reads_it():
    assert EXPECTED_SCHEMAS["users"]["age"] == "int"
    with pytest.raises(SchemaError, match="age"):
        enforce_schema(sample_frame("users").drop(columns=["age"]), "users")
