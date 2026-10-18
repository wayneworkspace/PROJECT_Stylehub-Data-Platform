"""One-time setup: build the partitioned Bronze events table."""

from functools import partial
from importlib import import_module

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from src.utils.logger import get_logger

bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")
retry = import_module("src.1_source.retry")

log = get_logger(__name__)

SOURCE_TABLE = "events"
TABLE = "events_partitioned"
RAW_COPY = "events_raw"  # temporary copy, deleted after the build
SQL_FILE = config.SQL_DIR / "bronze" / "01_events_partitioned.sql"


def copy_events(client: bigquery.Client, cfg: config.Settings) -> int:
    """Copy course events into Bronze; return the copied row count."""
    source_id = f"{cfg.project}.{cfg.source}.{SOURCE_TABLE}"
    target_id = f"{cfg.project}.{cfg.bronze}.{RAW_COPY}"
    source_location = client.get_dataset(f"{cfg.project}.{cfg.source}").location
    job_config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)

    def copy_in(location: str) -> None:
        client.copy_table(source_id, target_id, job_config=job_config, location=location).result()

    # Try the target region first, then the source region.
    for location in dict.fromkeys([cfg.location, source_location]):
        try:
            retry.call_with_retry(partial(copy_in, location))
            break
        except NotFound:
            log.warning("copy job not found in %s, trying the next region", location)
    else:
        raise RuntimeError("The copy job could not run in either region.")
    return retry.call_with_retry(lambda: client.get_table(target_id)).num_rows


def events_table_exists(cfg: config.Settings) -> bool:
    return bq.table_exists(config.bq_client(cfg), f"{cfg.project}.{cfg.bronze}.{TABLE}")


def ensure_events_bronze(cfg: config.Settings) -> None:
    """Build the table if missing, then delete the raw copy."""
    if events_table_exists(cfg):
        log.info("%s already exists, skipping the events build", TABLE)
        return
    client = config.bq_client(cfg)
    log.info("%s is missing: copying events, then building it (a few minutes)", TABLE)
    log.info("%s: %s rows copied", RAW_COPY, f"{copy_events(client, cfg):,}")
    sql = bq.render_sql(SQL_FILE, cfg)
    retry.call_with_retry(lambda: client.query(sql, job_config=bq.query_config(cfg)).result())
    raw_id = f"{cfg.project}.{cfg.bronze}.{RAW_COPY}"
    retry.call_with_retry(lambda: client.delete_table(raw_id, not_found_ok=True))
    log.info("%s built, %s deleted", TABLE, RAW_COPY)


def main() -> None:
    ensure_events_bronze(config.settings())


if __name__ == "__main__":
    main()
