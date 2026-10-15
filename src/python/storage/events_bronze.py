"""Build the Bronze events table if it does not exist yet (part of the Bronze step).

`events` is 108 million rows and does not change, so it is built once:
1. copy the course table to Bronze (storage/copy_events.py), because it sits in another region;
2. run src/sql/bronze/01_events_partitioned.sql to make the partitioned table.

If `events_partitioned` already exists, this does nothing. To rebuild it on purpose, delete the
table in BigQuery first, or run the two commands by hand:
    python -m storage.copy_events
    python -m transform.run_sql bronze

Usage: python -m storage.events_bronze
"""

import logging

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from common.config import settings
from common.retry import call_with_retry
from storage.copy_events import copy_events
from transform.run_sql import run_layer

log = logging.getLogger(__name__)

TABLE = "events_partitioned"


def events_table_exists() -> bool:
    cfg = settings()
    client = bigquery.Client(project=cfg.project)
    try:
        call_with_retry(lambda: client.get_table(f"{cfg.project}.{cfg.bronze}.{TABLE}"))
    except NotFound:
        return False
    return True


def ensure_events_bronze() -> bool:
    """Build the table when it is missing. Return True if it was built, False if it was there."""
    if events_table_exists():
        log.info("%s already exists, skipping the events build", TABLE)
        return False
    log.info("%s is missing: copying events, then building it (a few minutes)", TABLE)
    rows = copy_events()
    log.info("events_raw: %s rows copied", rows)
    run_layer("bronze")
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print("built" if ensure_events_bronze() else "already there")


if __name__ == "__main__":
    main()
