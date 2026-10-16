"""Build the Bronze events table once. This is a SET-UP step, not part of the daily run.

`events` is 108 million rows and does not change, so it is built one time:
1. copy the course table to Bronze (bronze/copy_events.py), because it sits in another region;
2. run src/stylehub/sql/bronze/01_events_partitioned.sql to make the partitioned table;
3. delete the 15 GB copy `events_raw`, so you do not pay to store the data twice.

The daily Bronze step only CHECKS that `events_partitioned` exists and fails with a clear message
if it does not. If it already exists, this command does nothing. To rebuild it on purpose, delete
the table in BigQuery first.

Usage: python -m stylehub.bronze.events_bronze [--keep-raw]
"""

import argparse
import logging

from google.cloud import bigquery

from stylehub.bronze.copy_events import copy_events
from stylehub.bronze.run_sql import run_layer
from stylehub.common.bq import table_exists
from stylehub.common.config import Settings, resolve
from stylehub.common.retry import call_with_retry

log = logging.getLogger(__name__)

TABLE = "events_partitioned"
RAW_COPY = "events_raw"  # made by copy_events, only needed to build the partitioned table
SQL_FILE = "01_events_partitioned.sql"
EVENTS_BOOTSTRAP_COMMAND = "uv run python -m stylehub.bronze.events_bronze"


def events_table_exists(client: bigquery.Client | None = None, cfg: Settings | None = None) -> bool:
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
    return table_exists(client, f"{cfg.project}.{cfg.bronze}.{TABLE}")


def drop_raw_copy(client: bigquery.Client | None = None, cfg: Settings | None = None) -> None:
    """Delete the 15 GB copy once the partitioned table is built."""
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
    call_with_retry(
        lambda: client.delete_table(f"{cfg.project}.{cfg.bronze}.{RAW_COPY}", not_found_ok=True)
    )


def ensure_events_bronze(keep_raw: bool = False) -> bool:
    """Build the table when it is missing. Return True if it was built, False if it was there."""
    if events_table_exists():
        log.info("%s already exists, skipping the events build", TABLE)
        return False
    log.info("%s is missing: copying events, then building it (a few minutes)", TABLE)
    rows = copy_events()
    log.info("%s: %s rows copied", RAW_COPY, rows)
    run_layer("bronze", only_file=SQL_FILE)  # only this file, not every file in the folder
    if not events_table_exists():
        raise RuntimeError(f"{TABLE} was not created. Keeping {RAW_COPY} so you can look.")
    if not keep_raw:
        drop_raw_copy()
        log.info("%s deleted (use --keep-raw to keep it)", RAW_COPY)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-raw", action="store_true", help=f"do not delete {RAW_COPY}")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    log.info("built" if ensure_events_bronze(args.keep_raw) else "already there")


if __name__ == "__main__":
    main()
