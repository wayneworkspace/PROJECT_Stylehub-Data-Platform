"""Full load of the course CSV tables into the Raw Zone."""

import time
from datetime import UTC, date, datetime
from importlib import import_module

import pandas as pd

from src.utils.logger import get_logger

bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")
raw_writer = import_module("src.2_ingestion.raw_writer")
schema_check = import_module("src.2_ingestion.schema_check")

log = get_logger(__name__)

CSV_TABLES = ("orders", "order_items", "products", "users")
# GEOGRAPHY column; plain Parquet in Raw cannot hold it.
DROP_COLUMNS = {"users": ["user_geom"]}
# Older labels would hold today's data under an old date.
MAX_LABEL_AGE_DAYS = 3


class SourceRowMismatch(RuntimeError):
    """Rows read differ from the source table's row count."""


def warn_if_backdated(data_date: str) -> None:
    """Warn when data_date is older than MAX_LABEL_AGE_DAYS days."""
    age_days = (datetime.now(UTC).date() - date.fromisoformat(data_date)).days
    if age_days > MAX_LABEL_AGE_DAYS:
        log.warning(
            "data_date %s is %d days old, but the source is read as it is TODAY. The Raw folder "
            "date=%s will hold today's data, not the data of that day.",
            data_date,
            age_days,
            data_date,
        )


def extract_full(table: str, cfg: config.Settings) -> pd.DataFrame:
    """Read every row of one table, checking schema and row count."""
    if table not in CSV_TABLES:
        raise ValueError(f"No CSV table configured: {table}")
    client = config.bq_client(cfg)
    table_id = f"{cfg.project}.{cfg.source}.{table}"
    source = retry.call_with_retry(lambda: client.get_table(table_id))
    dropped = DROP_COLUMNS.get(table, [])
    schema_check.check_declared_schema(table, [f for f in source.schema if f.name not in dropped])
    # Safe: table comes from CSV_TABLES, dataset from settings.
    query = f"SELECT * FROM `{table_id}`"  # noqa: S608
    df = retry.call_with_retry(
        lambda: client.query(query, job_config=bq.query_config(cfg)).to_dataframe()
    )
    if source.num_rows is not None and len(df) != source.num_rows:
        raise SourceRowMismatch(f"{table}: read {len(df)} rows, the source has {source.num_rows}")
    return schema_check.type_empty_columns(df.drop(columns=dropped, errors="ignore"), table)


def ingest_table(table: str, data_date: str, cfg: config.Settings) -> int:
    """Write one CSV table to the Raw Zone; return its row count."""
    warn_if_backdated(data_date)
    started = time.perf_counter()
    df = extract_full(table, cfg)
    uri = raw_writer.write_raw(df, table, data_date, cfg)
    seconds = time.perf_counter() - started
    log.info("%s %s: %s rows (%.1fs) -> %s", table, data_date, len(df), seconds, uri)
    return len(df)
