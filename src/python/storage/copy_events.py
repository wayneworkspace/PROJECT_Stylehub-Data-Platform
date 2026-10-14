"""Copy the big events table from the course dataset to the Bronze dataset (one time).

The course dataset (`stylehub`) is in the US. Bronze is in the region of GCP_LOCATION
(asia-southeast1). A BigQuery query cannot read one region and write to another, so the table
is copied first with a copy job. The copy is stored as `<bronze>.events_raw`. After that, the SQL
file src/sql/bronze/01_events_partitioned.sql builds the partitioned table from it.

A copy job across regions is free to run, but Google may charge for the data that crosses regions.
Run it once. A second run replaces the copy.

Usage: python -m storage.copy_events
"""

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from common.config import settings
from common.retry import call_with_retry

SOURCE_TABLE = "events"
TARGET_TABLE = "events_raw"


def copy_events() -> int:
    """Copy the table. Return the number of rows in the copy."""
    cfg = settings()
    client = bigquery.Client(project=cfg.project)
    source_id = f"{cfg.project}.{cfg.source}.{SOURCE_TABLE}"
    target_id = f"{cfg.project}.{cfg.bronze}.{TARGET_TABLE}"
    source_location = client.get_dataset(f"{cfg.project}.{cfg.source}").location

    config = bigquery.CopyJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    # Try the region of the target first, then the region of the source.
    for location in dict.fromkeys([cfg.location, source_location]):
        try:
            call_with_retry(
                lambda: client.copy_table(
                    source_id, target_id, job_config=config, location=location
                ).result()
            )
            break
        except NotFound:
            print(f"copy job not found in {location}, trying the next region")
    else:
        raise SystemExit("The copy job could not run in either region.")
    return client.get_table(target_id).num_rows


def main() -> None:
    print(f"{TARGET_TABLE}: {copy_events():,} rows copied")


if __name__ == "__main__":
    main()
