"""Notice when the source changes its columns, before the data reaches the Raw Zone.

The source team can add, drop, rename or retype a column and tell nobody. A pipeline that does
not look stays green and quietly gives wrong numbers.

The expected columns are listed once, in the dbt sources file (_stylehub__sources.yaml), with a
simple type: int, number (decimal or float), text, datetime.

| Change         | Reaction                                           |
|----------------|----------------------------------------------------|
| New column     | Warning only: nothing reads it yet                 |
| Removed column | Stop (a rename looks like one removed + one new)   |
| Type changed   | Stop: casts and sums may break                     |
"""

import logging
from collections.abc import Iterable
from functools import cache
from typing import Any

import pandas as pd
import yaml

from stylehub.common.config import DBT_DIR

log = logging.getLogger(__name__)

SOURCES_FILE = DBT_DIR / "models" / "staging" / "stylehub" / "_stylehub__sources.yaml"


@cache
def expected_schemas() -> dict[str, dict[str, str]]:
    """{table: {column: type}} from the dbt sources file. Tables with no columns are not checked."""
    tables = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["sources"][0]["tables"]
    return {t["name"]: {c["name"]: c["data_type"] for c in t.get("columns", [])} for t in tables}


class SchemaError(Exception):
    """The source columns no longer match what the pipeline expects."""


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


def check_declared_schema(table: str, fields: Iterable[Any], on_change: str = "fail") -> None:
    """Compare the columns the source table DECLARES with the expected schema.

    This reads table metadata only, so a changed source stops the run BEFORE any row is read.
    `fields` are BigQuery schema fields (name, field_type). A table with no expected schema
    is not checked.

    on_change="fail": a missing or retyped column stops the run.
    on_change="absorb": a missing column only warns (add_missing_columns fills it with NULL). A
    new column always passes with a warning. A retyped column always stops the run.
    """
    expected = expected_schemas().get(table)
    if not expected:
        return
    declared = {f.name: BQ_KIND_NAMES.get(str(f.field_type).upper()) for f in fields}
    added = [col for col in declared if col not in expected]
    removed = [col for col in expected if col not in declared]
    retyped = [
        f"{col} ({want} -> {declared[col]})"
        for col, want in expected.items()
        if declared.get(col) not in (None, want) and col in declared
    ]
    if added:
        log.warning("%s: new columns in the source: %s", table, ", ".join(added))
    problems = []
    if removed and on_change == "absorb":
        log.warning("%s: missing columns will be NULL: %s", table, ", ".join(removed))
    elif removed:
        problems.append(f"missing columns: {', '.join(removed)}")
    if retyped:
        problems.append(f"type changes: {', '.join(retyped)}")
    if problems:
        raise SchemaError(f"{table}: the source table changed: {'; '.join(problems)}")


# The pandas type that gives an EMPTY column the type the source really has.
EMPTY_COLUMN_DTYPES = {
    "int": "Int64",
    "number": "float64",
    "text": "string",
    "datetime": "datetime64[ns, UTC]",
}


def type_empty_columns(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Give every expected column that holds only NULLs its real type.

    Parquet writes a column of only NULLs with the type "null". BigQuery then loads that day with
    another type than the other days. With the expected type written down, every day has the
    same one. A table with no expected schema is returned as it is.
    """
    expected = expected_schemas().get(table, {})
    empty = [c for c in expected if c in df.columns and df[c].dropna().empty]
    return df.astype({c: EMPTY_COLUMN_DTYPES[expected[c]] for c in empty}) if empty else df


def add_missing_columns(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Add every expected column that the source no longer has, filled with NULL."""
    missing = [c for c in expected_schemas().get(table, {}) if c not in df.columns]
    return df.assign(**dict.fromkeys(missing)) if missing else df
