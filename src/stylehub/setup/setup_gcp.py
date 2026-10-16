"""Create the GCS bucket and the BigQuery datasets (session 1, exercise 1).

Safe to run again: anything that already exists is left alone. New ones are created in
GCP_LOCATION. The bucket and the datasets should share one location, or loads between them fail.

Usage: python -m stylehub.setup.setup_gcp [--dry-run]
"""

import argparse
import logging

import google.cloud.storage as storage
from google.cloud import bigquery

from stylehub.common.config import SQL_DIR, Settings, settings
from stylehub.common.logs import setup_cli_logging
from stylehub.common.sql import render_sql

log = logging.getLogger(__name__)


def dataset_ids(cfg: Settings) -> list[str]:
    """Course source dataset first, then the layers (staging holds personal data) and ops."""
    return [cfg.source, cfg.bronze, cfg.staging, cfg.silver, cfg.gold, cfg.ops]


# Raw keeps a full copy of the source every day, so without a rule it only grows. Old copies of a
# file (versioning) and old daily batches are deleted. A person's data therefore leaves Raw after
# at most RAW_RETENTION_DAYS + NONCURRENT_RETENTION_DAYS days (see docs/design/DECISIONS.md).
RAW_RETENTION_DAYS = 90
NONCURRENT_RETENTION_DAYS = 30


def ensure_lifecycle(bucket: storage.Bucket, raw_prefix: str) -> bool:
    """Add the delete rules if the bucket does not have them. Return True if it changed them."""
    rules = [dict(rule) for rule in bucket.lifecycle_rules]
    wanted = [
        {
            "action": {"type": "Delete"},
            "condition": {"daysSinceNoncurrentTime": NONCURRENT_RETENTION_DAYS},
        },
        {
            "action": {"type": "Delete"},
            "condition": {"age": RAW_RETENTION_DAYS, "matchesPrefix": [f"{raw_prefix}/"]},
        },
    ]
    missing = [rule for rule in wanted if rule not in rules]
    if not missing:
        return False
    bucket.lifecycle_rules = rules + missing
    bucket.patch()
    return True


def ensure_bucket(client: storage.Client, name: str, location: str) -> bool:
    """Create the bucket if it is missing. Return True if it was created."""
    if client.lookup_bucket(name) is not None:
        return False
    bucket = client.bucket(name)
    bucket.iam_configuration.uniform_bucket_level_access_enabled = True  # no per-file ACLs
    # Raw is the copy that Bronze can be rebuilt from, and there is no other backup. With versioning
    # on, a file that is overwritten or deleted by mistake can be brought back.
    bucket.versioning_enabled = True
    client.create_bucket(bucket, location=location)
    return True


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    """Create the dataset if it is missing. An existing dataset is left alone."""
    dataset = bigquery.Dataset(f"{client.project}.{dataset_id}")
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)


def ensure_ops_tables(client: bigquery.Client) -> list[str]:
    """Create the pipeline_runs table and apply its migrations (src/stylehub/sql/ops/).

    This is set-up work, so it runs here once. The daily pipeline does not change the table.
    Return the names of the SQL files that ran.
    """
    names = []
    for path in sorted((SQL_DIR / "ops").glob("*.sql")):
        client.query(render_sql(path)).result()
        names.append(path.name)
    return names


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only print what would be created")
    args = parser.parse_args()
    setup_cli_logging()
    cfg = settings()

    if args.dry_run:
        log.info(f"Would make sure this exists in {cfg.location} (project {cfg.project}):")
        log.info(f"  bucket   gs://{cfg.bucket} (delete rules: Raw {RAW_RETENTION_DAYS} days)")
        for dataset_id in dataset_ids(cfg):
            log.info(f"  dataset  {dataset_id}")
        log.info("  table    pipeline_runs (src/stylehub/sql/ops/)")
        return

    storage_client = storage.Client(project=cfg.project)
    created = ensure_bucket(storage_client, cfg.bucket, cfg.location)
    log.info(f"bucket   gs://{cfg.bucket}: {'created' if created else 'already exists'}")
    bucket = storage_client.get_bucket(cfg.bucket)
    changed = ensure_lifecycle(bucket, cfg.raw_prefix)
    log.info(f"lifecycle gs://{cfg.bucket}: {'rules added' if changed else 'rules already there'}")

    bigquery_client = bigquery.Client(project=cfg.project)
    for dataset_id in dataset_ids(cfg):
        ensure_dataset(bigquery_client, dataset_id, cfg.location)
        log.info(f"dataset  {dataset_id}: ready")
    for name in ensure_ops_tables(bigquery_client):
        log.info(f"ops      {name}: done")


if __name__ == "__main__":
    main()
