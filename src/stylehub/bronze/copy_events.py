"""Copy the big events table from the course dataset to the Bronze dataset (one time).

The course dataset (`stylehub`) is in the US. Bronze is in the region of GCP_LOCATION
(asia-southeast1). A BigQuery query cannot read one region and write to another, so the table
is copied first with a copy job. The copy is stored as `<bronze>.events_raw`. After that, the SQL
file src/stylehub/sql/bronze/01_events_partitioned.sql builds the partitioned table from it.

A copy job across regions is free to run, but Google may charge for the data that crosses regions.
Run it once. A second run replaces the copy.

Usage: python -m stylehub.bronze.copy_events
"""

import logging
from functools import partial

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from stylehub.common.config import Settings, resolve
from stylehub.common.retry import call_with_retry

log = logging.getLogger(__name__)

SOURCE_TABLE = "events"
TARGET_TABLE = "events_raw"


def copy_events(client: bigquery.Client | None = None, cfg: Settings | None = None) -> int:
    """Copy the table. Return the number of rows in the copy. Pass `client` to use your own."""
    cfg = resolve(cfg)
    client = client or bigquery.Client(project=cfg.project)
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info("%s: %s rows copied", TARGET_TABLE, f"{copy_events():,}")


if __name__ == "__main__":
    main()
