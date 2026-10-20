"""Incremental load of the course Postgres tables into the Raw Zone."""

import time
from datetime import datetime, timedelta
from importlib import import_module
from types import SimpleNamespace

import pandas as pd
import pyarrow as pa
from sqlalchemy import text

get_logger = import_module("src.0_utils.logger").get_logger

bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")
utils = import_module("src.1_source.utils")
raw_writer = import_module("src.2_ingestion.raw_writer")
schema_check = import_module("src.2_ingestion.schema_check")

log = get_logger(__name__)

PG_TABLES = ("orders", "order_items", "products", "shipments", "users")
WATERMARK = "updated_at"  # catches new and changed rows; naive UTC time
LOOKBACK_DAYS = 1  # re-read late writes; Silver removes the duplicates
CHUNK_ROWS = 50_000  # rows held in memory at once; one Raw part file per chunk
# Postgres type -> Parquet type; DECIMAL(38, 9) loads as BigQuery NUMERIC.
PG_ARROW_TYPES = {
    "bigint": pa.int64(),
    "integer": pa.int64(),
    "smallint": pa.int64(),
    "numeric": pa.decimal128(38, 9),
    "double precision": pa.float64(),
    "real": pa.float64(),
    "text": pa.string(),
    "character varying": pa.string(),
    # Microseconds: BigQuery reads nanosecond Parquet timestamps as INTEGER.
    "timestamp without time zone": pa.timestamp("us"),
    "timestamp with time zone": pa.timestamp("us", tz="UTC"),
}


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
    table_id = f"{cfg.project}.{cfg.bronze}.{raw_name(table)}"
    return bq.newest_before(table_id, WATERMARK, data_date, cfg)


def arrow_schema(table: str, columns: list[tuple[str, str]]) -> pa.Schema:
    """Parquet schema from Postgres column types, the same for every chunk."""
    unknown = sorted({kind for _, kind in columns if kind not in PG_ARROW_TYPES})
    if unknown:
        raise schema_check.SchemaError(
            f"{table}: no Parquet type for Postgres type {', '.join(unknown)}; "
            "add it to PG_ARROW_TYPES"
        )
    return pa.schema([(name, PG_ARROW_TYPES[kind]) for name, kind in columns])


def extract_to_raw(
    table: str,
    start: datetime | None,
    end: datetime,
    schema: pa.Schema,
    data_date: str,
    cfg: config.Settings,
) -> int:
    """Stream the window in chunks into one Raw batch; return the rows written.

    One consistent snapshot, checked against the source row count. _SUCCESS is
    written last, so a failed attempt is never loaded (the pipeline account may
    not delete Raw files); a retry writes a new, later batch.
    """
    if table not in PG_TABLES:
        raise ValueError(f"No Postgres table configured: {table}")
    where = f"{WATERMARK} < :end" + ("" if start is None else f" AND {WATERMARK} >= :start")
    params = {"start": start, "end": end}

    def read() -> int:
        batch_id, written = utils.new_id(), 0
        with config.pg_engine(cfg).connect() as conn:
            # stream_results: a server-side cursor sends one chunk at a time.
            conn = conn.execution_options(isolation_level="REPEATABLE READ", stream_results=True)
            # Safe: the table name comes from PG_TABLES.
            count = text(f'SELECT COUNT(*) FROM "{table}" WHERE {where}')  # noqa: S608
            expected = conn.execute(count, params).scalar_one()
            query = text(f'SELECT * FROM "{table}" WHERE {where}')  # noqa: S608
            chunks = pd.read_sql(
                query, conn, params=params, coerce_float=False, chunksize=CHUNK_ROWS
            )
            for part, chunk in enumerate(chunks):
                if chunk.empty:  # pandas yields one empty chunk when nothing matched
                    continue
                raw_writer.write_raw(
                    chunk,
                    raw_name(table),
                    data_date,
                    cfg,
                    source="postgres",
                    batch_id=batch_id,
                    part=f"part_{part:05d}",
                    schema=schema,
                )
                written += len(chunk)
        if written != expected:
            raise SourceRowMismatch(f"{table}: read {written} rows, the source has {expected}")
        if written:
            raw_writer.mark_batch_complete(raw_name(table), data_date, batch_id, cfg)
        return written

    return retry.call_with_retry(read)


def check_schema(table: str, cfg: config.Settings) -> pa.Schema:
    """Stop before reading rows when Postgres columns changed (dbt sources file).

    Returns the Parquet schema to write, in the table's column order.
    """
    sql = text(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :table ORDER BY ordinal_position"
    )

    def read() -> list:
        with config.pg_engine(cfg).connect() as conn:
            return conn.execute(sql, {"table": table}).all()

    columns = [(name, kind) for name, kind in retry.call_with_retry(read)]
    fields = [SimpleNamespace(name=n, field_type=t) for n, t in columns]
    schema_check.check_declared_schema(
        raw_name(table), fields, source="stylehub_pg", kinds=schema_check.PG_KIND_NAMES
    )
    return arrow_schema(table, columns)


def ingest_table(table: str, data_date: str, cfg: config.Settings) -> int:
    """Write the rows changed in the window to Raw; return the row count."""
    started = time.perf_counter()
    schema = check_schema(table, cfg)
    start, end = read_window(data_date, bronze_watermark(table, data_date, cfg))
    rows = extract_to_raw(table, start, end, schema, data_date, cfg)
    seconds = time.perf_counter() - started
    if rows == 0:
        log.info("%s %s: no changed rows since %s", table, data_date, start)
        return 0
    log.info("%s %s: %s rows from %s (%.1fs) -> Raw", table, data_date, rows, start, seconds)
    return rows
