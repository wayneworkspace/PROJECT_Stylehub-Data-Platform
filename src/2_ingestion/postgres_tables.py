"""Incremental load of the course Postgres tables into the Raw Zone."""

import time
from datetime import datetime, timedelta
from importlib import import_module

import pandas as pd
from sqlalchemy import text

get_logger = import_module("src.0_utils.logger").get_logger

bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")
raw_writer = import_module("src.2_ingestion.raw_writer")

log = get_logger(__name__)

PG_TABLES = ("orders", "order_items", "products", "shipments", "users")
WATERMARK = "updated_at"  # catches new and changed rows; naive UTC time
LOOKBACK_DAYS = 1  # re-read late writes; Silver removes the duplicates
CHUNK_ROWS = 100_000


class SourceRowMismatch(RuntimeError):
    """Rows read differ from the source count for the same window."""


def raw_name(table: str) -> str:
    """Raw and Bronze name, kept apart from the CSV tables."""
    return f"pg_{table}"


def read_window(data_date: str, watermark: datetime | None) -> tuple[datetime | None, datetime]:
    """Rows to read: watermark minus lookback, up to the end of data_date."""
    end = datetime.fromisoformat(data_date) + timedelta(days=1)
    start = None if watermark is None else watermark - timedelta(days=LOOKBACK_DAYS)
    return start, end  # start None means the first, full load


def bronze_watermark(table: str, data_date: str, cfg: config.Settings) -> datetime | None:
    """Newest updated_at in Bronze before data_date, so reruns read the same window."""
    client = config.bq_client(cfg)
    table_id = f"{cfg.project}.{cfg.bronze}.{raw_name(table)}"
    if not bq.table_exists(client, table_id):
        return None
    sql = (
        f"SELECT MAX({WATERMARK}) FROM `{table_id}` "  # noqa: S608
        f"WHERE _PARTITIONDATE < DATE '{data_date}'"
    )
    rows = retry.call_with_retry(lambda: list(client.query(sql, job_config=bq.query_config(cfg))))
    return rows[0][0]


def extract(
    table: str, start: datetime | None, end: datetime, cfg: config.Settings
) -> pd.DataFrame:
    """Read the window in one consistent snapshot and check the row count."""
    if table not in PG_TABLES:
        raise ValueError(f"No Postgres table configured: {table}")
    where = f"{WATERMARK} < :end" + ("" if start is None else f" AND {WATERMARK} >= :start")
    params = {"start": start, "end": end}

    def read() -> pd.DataFrame:
        with config.pg_engine(cfg).connect() as conn:
            conn = conn.execution_options(isolation_level="REPEATABLE READ")
            # Safe: the table name comes from PG_TABLES.
            count = text(f'SELECT COUNT(*) FROM "{table}" WHERE {where}')  # noqa: S608
            expected = conn.execute(count, params).scalar_one()
            query = text(f'SELECT * FROM "{table}" WHERE {where}')  # noqa: S608
            chunks = pd.read_sql(
                query, conn, params=params, chunksize=CHUNK_ROWS, coerce_float=False
            )
            df = pd.concat(chunks, ignore_index=True)
        if len(df) != expected:
            raise SourceRowMismatch(f"{table}: read {len(df)} rows, the source has {expected}")
        return df

    return retry.call_with_retry(read)


def ingest_table(table: str, data_date: str, cfg: config.Settings) -> int:
    """Write the rows changed in the window to Raw; return the row count."""
    started = time.perf_counter()
    start, end = read_window(data_date, bronze_watermark(table, data_date, cfg))
    df = extract(table, start, end, cfg)
    seconds = time.perf_counter() - started
    if df.empty:
        log.info("%s %s: no changed rows since %s", table, data_date, start)
        return 0
    uri = raw_writer.write_raw(df, raw_name(table), data_date, cfg, source="postgres")
    log.info("%s %s: %s rows from %s (%.1fs) -> %s", table, data_date, len(df), start, seconds, uri)
    return len(df)
