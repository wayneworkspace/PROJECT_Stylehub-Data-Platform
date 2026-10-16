"""Notice when the source changes its columns, before the data reaches the Raw Zone (session 2).

The source team can add, drop, rename or retype a column and tell nobody. A pipeline that
does not look will stay green and quietly give wrong numbers.

EXPECTED_SCHEMAS lists the columns that the Silver models (dbt/models/staging/) need,
with a simple type: int, number (decimal or float), text, datetime.
How each kind of change is handled:

| Change         | What it means                      | Reaction                                 |
|----------------|------------------------------------|------------------------------------------|
| New column     | Usually safe, nothing reads it yet | Warning only                             |
| Removed column | Silver or Gold may break           | fail: stop. absorb: fill NULL + warn     |
| Renamed column | Looks like one removed + one new   | Same as removed (the message says so)    |
| Type changed   | Casts and sums may break           | fail: stop. absorb: let it pass + warn   |

Check the expected columns against the real source before the first run on real data.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

log = logging.getLogger(__name__)

OnChange = Literal["fail", "absorb"]
ON_CHANGE_CHOICES = ("fail", "absorb")

EXPECTED_SCHEMAS: dict[str, dict[str, str]] = {
    "orders": {
        "order_id": "int",
        "user_id": "int",
        "status": "text",
        "created_at": "datetime",
        "shipped_at": "datetime",
        "delivered_at": "datetime",
        "returned_at": "datetime",
        "num_of_item": "int",
    },
    "order_items": {
        "id": "int",
        "order_id": "int",
        "user_id": "int",
        "product_id": "int",
        "status": "text",
        "created_at": "datetime",
        "shipped_at": "datetime",
        "delivered_at": "datetime",
        "returned_at": "datetime",
        "sale_price": "number",
    },
    "products": {
        "id": "int",
        "name": "text",
        "category": "text",
        "brand": "text",
        "department": "text",
        "sku": "text",
        "cost": "number",
        "retail_price": "number",
    },
    "users": {
        "id": "int",
        "email": "text",
        "age": "int",
        "gender": "text",
        "state": "text",
        "city": "text",
        "country": "text",
        "latitude": "number",
        "longitude": "number",
        "traffic_source": "text",
        "created_at": "datetime",
    },
}


class SchemaError(Exception):
    """The source columns no longer match what the pipeline expects."""


@dataclass(frozen=True)
class SchemaDiff:
    added: list[str] = field(default_factory=list)  # in the data, not expected
    removed: list[str] = field(default_factory=list)  # expected, not in the data
    retyped: dict[str, tuple[str, str]] = field(default_factory=dict)  # column -> (expected, found)

    @property
    def is_breaking(self) -> bool:
        return bool(self.removed or self.retyped)

    def describe(self) -> str:
        lines = []
        if self.removed:
            lines.append(f"missing columns: {', '.join(self.removed)}")
        if self.retyped:
            changes = [f"{c} ({want} -> {got})" for c, (want, got) in self.retyped.items()]
            lines.append(f"type changes: {', '.join(changes)}")
        if self.added:
            lines.append(f"new columns: {', '.join(self.added)}")
        if self.removed and self.added:
            lines.append("a renamed column looks like one missing plus one new column")
        return "; ".join(lines)


# pandas names -> our simple names. A name that is not here (for example "mixed") is kept as it is.
KIND_NAMES = {
    "boolean": "bool",
    "integer": "int",
    "floating": "number",
    "decimal": "number",
    "mixed-integer-float": "number",
    "string": "text",
    "datetime": "datetime",
    "datetime64": "datetime",
}


def column_kind(series: pd.Series) -> str | None:
    """Name the kind of a column. Return None when there is no value to look at."""
    if series.dropna().empty:
        return None
    inferred = pd.api.types.infer_dtype(series, skipna=True)  # looks at every value
    return KIND_NAMES.get(inferred, inferred)


def diff_schema(df: pd.DataFrame, expected: dict[str, str]) -> SchemaDiff:
    removed = [col for col in expected if col not in df.columns]
    added = [col for col in df.columns if col not in expected]
    retyped = {}
    for col, want in expected.items():
        if col in df.columns:
            got = column_kind(df[col])
            if got is not None and got != want:  # None = empty column, nothing to compare
                retyped[col] = (want, got)
    return SchemaDiff(added=added, removed=removed, retyped=retyped)


# BigQuery column types -> our simple names. A type that is not here (for example DATE) is not
# compared.
BQ_KIND_NAMES = {
    "INTEGER": "int",
    "INT64": "int",
    "FLOAT": "number",
    "FLOAT64": "number",
    "NUMERIC": "number",
    "BIGNUMERIC": "number",
    "STRING": "text",
    "TIMESTAMP": "datetime",
    "DATETIME": "datetime",
}


def check_declared_schema(
    table: str, fields: Iterable[Any], on_change: OnChange = "fail"
) -> SchemaDiff | None:
    """Compare the columns that the source table DECLARES with the expected schema.

    This reads table metadata only, so a changed source stops the run BEFORE gigabytes are read
    into memory. `fields` are BigQuery schema fields (name, field_type). Only on_change="fail"
    raises. The check on the real values (enforce_schema) still runs later. Return the diff, or
    None for a table that has no expected schema.
    """
    expected = EXPECTED_SCHEMAS.get(table)
    if expected is None:
        return None
    declared = {f.name: BQ_KIND_NAMES.get(str(f.field_type).upper()) for f in fields}
    diff = SchemaDiff(
        added=[col for col in declared if col not in expected],
        removed=[col for col in expected if col not in declared],
        retyped={
            col: (want, str(declared[col]))
            for col, want in expected.items()
            if declared.get(col) not in (None, want) and col in declared
        },
    )
    if diff.is_breaking and on_change == "fail":
        raise SchemaError(f"{table}: the source table changed: {diff.describe()}")
    return diff


# The pandas type that gives an EMPTY column the type the source really has.
EMPTY_COLUMN_DTYPES = {
    "int": "Int64",
    "number": "float64",
    "text": "string",
    "datetime": "datetime64[ns, UTC]",
}


def type_empty_columns(df: pd.DataFrame, expected: dict[str, str]) -> pd.DataFrame:
    """Give every expected column that holds no value its real type.

    diff_schema cannot compare an empty column (there is no value to look at), and Parquet writes
    a column of only NULLs with the type "null". BigQuery then loads that day with another type
    than the other days. With the expected type written down, every day has the same one.
    Returns the same object when nothing needs to change.
    """
    empty = [c for c in expected if c in df.columns and column_kind(df[c]) is None]
    if not empty:
        return df
    typed = df.copy()
    for col in empty:
        typed[col] = typed[col].astype(EMPTY_COLUMN_DTYPES[expected[col]])
    return typed


def enforce_schema(df: pd.DataFrame, table: str, on_change: OnChange = "fail") -> pd.DataFrame:
    """Compare the columns with the expected schema. Return the data to write.

    A table without an entry in EXPECTED_SCHEMAS is not checked.
    """
    if on_change not in ON_CHANGE_CHOICES:
        raise ValueError(f"on_change must be one of {ON_CHANGE_CHOICES}, got: {on_change}")
    expected = EXPECTED_SCHEMAS.get(table)
    if expected is None:
        return df

    diff = diff_schema(df, expected)
    if diff.added:
        log.warning("%s: new columns in the source: %s", table, ", ".join(diff.added))
    if not diff.is_breaking:
        return type_empty_columns(df, expected)

    if on_change == "fail":
        raise SchemaError(f"{table}: the source schema changed: {diff.describe()}")

    log.warning("%s: absorbing a schema change: %s", table, diff.describe())
    absorbed = df.copy()
    for col in diff.removed:
        absorbed[col] = None
    return type_empty_columns(absorbed, expected)
