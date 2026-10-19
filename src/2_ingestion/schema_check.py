"""Stop the run when source columns change, before reading rows."""

from collections.abc import Iterable
from functools import cache
from importlib import import_module
from typing import Any

import pandas as pd
import yaml

get_logger = import_module("src.0_utils.logger").get_logger

config = import_module("src.1_source.config")

log = get_logger(__name__)

STAGING = config.DBT_DIR / "models" / "staging"
SOURCE_FILES = {
    "stylehub": STAGING / "stylehub" / "_stylehub__sources.yaml",
    "stylehub_pg": STAGING / "stylehub_pg" / "_stylehub_pg__sources.yaml",
}


@cache
def expected_schemas(source: str = "stylehub") -> dict[str, dict[str, str]]:
    """{table: {column: type}} read from one dbt sources file."""
    text = SOURCE_FILES[source].read_text(encoding="utf-8")
    tables = yaml.safe_load(text)["sources"][0]["tables"]
    return {t["name"]: {c["name"]: c["data_type"] for c in t.get("columns", [])} for t in tables}


class SchemaError(Exception):
    """Source columns no longer match the expected schema."""


# BigQuery types mapped to our simple type names.
BQ_KIND_NAMES = {
    "INTEGER": "int",
    "FLOAT": "number",
    "NUMERIC": "number",
    "BIGNUMERIC": "number",
    "STRING": "text",
    "TIMESTAMP": "datetime",
    "DATETIME": "datetime",
}
# Postgres information_schema types mapped to the same names.
PG_KIND_NAMES = {
    "bigint": "int",
    "integer": "int",
    "smallint": "int",
    "numeric": "number",
    "double precision": "number",
    "real": "number",
    "text": "text",
    "character varying": "text",
    "timestamp without time zone": "datetime",
    "timestamp with time zone": "datetime",
}


def check_declared_schema(
    table: str,
    fields: Iterable[Any],
    source: str = "stylehub",
    kinds: dict[str, str] = BQ_KIND_NAMES,
) -> None:
    """Compare declared columns (.name, .field_type): warn on new, fail on missing or retyped."""
    expected = expected_schemas(source).get(table)
    if not expected:
        return
    declared = {f.name: kinds.get(f.field_type) for f in fields}
    added = [col for col in declared if col not in expected]
    removed = [col for col in expected if col not in declared]
    retyped = [
        f"{col} ({want} -> {declared[col]})"
        for col, want in expected.items()
        if declared.get(col) not in (None, want)
    ]
    if added:
        log.warning("%s: new columns in the source: %s", table, ", ".join(added))
    problems = []
    if removed:
        problems.append(f"missing columns: {', '.join(removed)}")
    if retyped:
        problems.append(f"type changes: {', '.join(retyped)}")
    if problems:
        raise SchemaError(f"{table}: the source table changed: {'; '.join(problems)}")


# pandas dtype for an all-NULL column of each type.
EMPTY_COLUMN_DTYPES = {
    "int": "Int64",
    "number": "float64",
    "text": "string",
    "datetime": "datetime64[ns, UTC]",
}


def type_empty_columns(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """Type all-NULL columns so every day's Parquet has one schema."""
    expected = expected_schemas().get(table, {})
    empty = [c for c in expected if c in df.columns and df[c].dropna().empty]
    return df.astype({c: EMPTY_COLUMN_DTYPES[expected[c]] for c in empty}) if empty else df
