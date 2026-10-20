"""Find rows deleted in Postgres: ids Bronze has that the source no longer has."""

from datetime import UTC, datetime
from importlib import import_module

import pandas as pd
from google.cloud import bigquery
from sqlalchemy import text

get_logger = import_module("src.0_utils.logger").get_logger
bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")
pg_tables = import_module("src.2_ingestion.postgres_tables")

log = get_logger(__name__)

TOMBSTONES = "pg_deleted_ids"  # Silver flags these ids is_deleted (macro latest_pg_rows)
SCHEMA = [
    bigquery.SchemaField("table_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("id", "INT64", mode="REQUIRED"),
    bigquery.SchemaField("detected_at", "TIMESTAMP", mode="REQUIRED"),
]


def source_ids(table: str, cfg: config.Settings) -> set[int]:
    """Every id the Postgres table has now."""

    def read() -> set[int]:
        with config.pg_engine(cfg).connect() as conn:
            # Safe: the table name comes from PG_TABLES.
            return set(conn.execute(text(f'SELECT id FROM "{table}"')).scalars())  # noqa: S608

    return retry.call_with_retry(read)


def bronze_ids(client: bigquery.Client, table: str, cfg: config.Settings) -> set[int]:
    """Every id Bronze ever loaded for the table."""
    table_id = f"{cfg.project}.{cfg.bronze}.{pg_tables.raw_name(table)}"
    sql = f"SELECT DISTINCT id FROM `{table_id}`"  # noqa: S608
    job = retry.call_with_retry(lambda: client.query(sql, job_config=bq.query_config(cfg)).result())
    return {row.id for row in job}


def known_deletions(client: bigquery.Client, target: str) -> dict[tuple[str, int], datetime]:
    """detected_at of ids already flagged, so deleted_at stays the first day seen."""
    if not bq.table_exists(client, target):
        return {}
    # list_rows reads the table without a billed query.
    frame = retry.call_with_retry(
        lambda: client.list_rows(target, selected_fields=SCHEMA).to_dataframe()
    )
    return {(r.table_name, r.id): r.detected_at for r in frame.itertuples()}


def reconcile(cfg: config.Settings) -> dict[str, int]:
    """Replace the tombstone table with today's full set; return counts per table."""
    client = config.bq_client(cfg)
    target = f"{cfg.project}.{cfg.bronze}.{TOMBSTONES}"
    known = known_deletions(client, target)
    now = datetime.now(UTC)
    rows, counts = [], {}
    for table in pg_tables.PG_TABLES:
        deleted = sorted(bronze_ids(client, table, cfg) - source_ids(table, cfg))
        counts[table] = len(deleted)
        rows += [
            {"table_name": table, "id": i, "detected_at": known.get((table, i), now)}
            for i in deleted
        ]
    frame = pd.DataFrame(rows, columns=[f.name for f in SCHEMA]).astype({"id": "Int64"})
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMA, write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    retry.call_with_retry(
        lambda: client.load_table_from_dataframe(frame, target, job_config=job_config).result()
    )
    log.info("deleted in Postgres, by table: %s", counts)
    return counts
