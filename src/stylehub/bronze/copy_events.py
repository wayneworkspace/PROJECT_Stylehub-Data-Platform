"""Copy the events table from the course dataset to the Bronze dataset (one time).

The course dataset is in another region than Bronze, and a query cannot read one region and write
to another. So a copy job makes `<bronze>.events_raw`, and then
src/stylehub/sql/bronze/01_events_partitioned.sql builds the partitioned table from it.

Usage: python -m stylehub.bronze.copy_events
"""

import logging
from functools import partial

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from stylehub.common.clients import bq_client
from stylehub.common.config import Settings, resolve
from stylehub.common.logs import setup_cli_logging
from stylehub.common.retry import call_with_retry

log = logging.getLogger(__name__)

SOURCE_TABLE = "events"
TARGET_TABLE = "events_raw"


def copy_events(client: bigquery.Client | None = None, cfg: Settings | None = None) -> int:
    """Copy the table. Return the number of rows in the copy. Pass `client` to use your own."""
    cfg = resolve(cfg)
    client = client or bq_client(cfg)
    source_id = f"{cfg.project}.{cfg.source}.{SOURCE_TABLE}"
    target_id = f"{cfg.project}.{cfg.bronze}.{TARGET_TABLE}"
    source_location = client.get_dataset(f"{cfg.project}.{cfg.source}").location

    config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)

    def copy_in(location: str) -> None:
        client.copy_table(source_id, target_id, job_config=config, location=location).result()

    # Try the region of the target first, then the region of the source.
    for location in dict.fromkeys([cfg.location, source_location]):
        try:
            call_with_retry(partial(copy_in, location))
            break
        except NotFound:
            log.warning("copy job not found in %s, trying the next region", location)
    else:
        raise RuntimeError("The copy job could not run in either region.")
    return call_with_retry(lambda: client.get_table(target_id)).num_rows


def main() -> None:
    setup_cli_logging()
    log.info("%s: %s rows copied", TARGET_TABLE, f"{copy_events():,}")


if __name__ == "__main__":
    main()
