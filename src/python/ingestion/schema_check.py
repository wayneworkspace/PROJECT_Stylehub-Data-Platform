"""Notice when the source changes its columns, before the data reaches the Raw Zone (session 2).

The source team can add, drop, rename or retype a column and tell nobody. A pipeline that
does not look will stay green and quietly give wrong numbers.

EXPECTED_SCHEMAS lists the columns that src/sql/silver/ and the watermark need, with a simple type:
int, number (decimal or float), text, datetime. How each kind of change is handled:

| Change         | What it means                      | Reaction                                 |
|----------------|------------------------------------|------------------------------------------|
| New column     | Usually safe, nothing reads it yet | Warning only                             |
| Removed column | Silver or Gold may break           | fail: stop. absorb: fill NULL + warn     |
| Renamed column | Looks like one removed + one new   | Same as removed (the message says so)    |
| Type changed   | Casts and sums may break           | fail: stop. absorb: let it pass + warn   |

Check the expected columns against the real source before the first run on real data.
"""

import logging
import numbers
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import pandas as pd

log = logging.getLogger(__name__)

OnChange = Literal["fail", "absorb"]
ON_CHANGE_CHOICES = ("fail", "absorb")

EXPECTED_SCHEMAS: dict[str, dict[str, str]] = {
    "orders": {
        "id": "int",
        "user_id": "int",
        "status": "text",
        "total_amount": "number",
        "created_at": "datetime",
        "updated_at": "datetime",
    },
    "order_items": {
        "id": "int",
        "order_id": "int",
        "product_id": "int",
        "sale_price": "number",
        "quantity": "int",
        "amount": "number",
        "created_at": "datetime",
        "updated_at": "datetime",
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


def column_kind(series: pd.Series) -> str | None:
    """Name the kind of a column. Return None when there is no value to look at."""
    values = series.dropna()
    if values.empty:
        return None
    if pd.api.types.is_bool_dtype(series.dtype):
        return "bool"
    if pd.api.types.is_integer_dtype(series.dtype):
        return "int"
    if pd.api.types.is_float_dtype(series.dtype):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "datetime"
    # Columns of mixed Python objects (Decimal, str, ...): look at the first value.
    value = values.iloc[0]
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, numbers.Integral):
        return "int"
    if isinstance(value, numbers.Number):  # float and Decimal
        return "number"
    if isinstance(value, datetime):
        return "datetime"
    if isinstance(value, str):
        return "text"
    return type(value).__name__


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
        return df

    if on_change == "fail":
        raise SchemaError(f"{table}: the source schema changed: {diff.describe()}")

    log.warning("%s: absorbing a schema change: %s", table, diff.describe())
    absorbed = df.copy()
    for col in diff.removed:
        absorbed[col] = None
    return absorbed
